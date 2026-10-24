# Simulador da ingestão

Serviço em Go que mantém a fila "viva" na demonstração: manda solicitações e eventos
clínicos mockados para a ingestão do backend, como um timer, sem parar.

- **uma entrada nova a cada 10 s** → `POST /v1/hospitais/<id>/fila/entradas`
- **a partir da primeira, um evento a cada 5 s** → `POST /v1/hospitais/<id>/fila/eventos`,
  sempre para a **última** entrada incluída

```
 0 s  + entrada A            15 s    evento → B
 5 s    evento → A           20 s    evento → B
10 s    evento → A           20 s  + entrada C
10 s  + entrada B            25 s    evento → C   …
```

Quando os dois vencem juntos, o evento sai antes da entrada: ele ainda é da entrada que
estava sendo trabalhada, e cada entrada recebe exatamente dois eventos (+5 s e +10 s).
Uma chamada que demora mais que o intervalo pula os tiques perdidos em vez de disparar em
rajada.

Só biblioteca padrão; nenhuma dependência.

## Como os pulos aparecem

Cada entrada sai de um de nove perfis (`internal/sim/catalog.go`), e cada perfil tem uma
história de eventos que piora o quadro. Como chegam dois eventos por entrada, os dois
primeiros passos de cada história são os que mudam a classe. Caminhos medidos contra o
dataset real (entrada → 1º evento → 2º evento):

| Perfil | Entra como | Dois primeiros eventos | Caminho na fila |
|---|---|---|---|
| colelitíase, hérnia, varizes, cálculo renal | D, sem urgência (fundo da fila) | PS → internação/PS | ~850 → ~550 → ~270 (D→C→B) |
| artrose de joelho | C | PS → PS | ~500 → ~410 → ~240 (C→B) |
| nódulo pulmonar (R91) | B | progressão → biópsia **positiva** | ~400 → ~330 → ~32 (B→A2) |
| lesão de mama (D48) | B | biópsia **positiva** → progressão | ~410 → ~70 → ~37 (B→A2) |
| câncer de cólon, de tireoide | A2 | progressão/piora → PS/progressão | ~85–185 → ~30 (A2→A1) |

Se os eventos vierem mais rápido que as entradas (`EVENT_INTERVAL` menor), a última entrada
anda o terceiro passo e depois recebe pioras genéricas. O log mostra cada pulo:

```
+ entrada  SOL-2026-90002 Valter Fagundes Silveira   cálculo renal            classe D  → posição 846
  evento   SOL-2026-90002 pronto_socorro/observacao            classe D→C   subiu 846 → 571 (+275)
  evento   SOL-2026-90002 internacao/alta                      classe C→B   subiu 571 → 251 (+320)
```

Os ids são `SOL-2026-9NNNN` / `PAC-9NNNN`, que não existem no dataset. Ao subir, o
simulador lê a fila: continua a numeração e adota os pacientes que ele mesmo criou antes
(sem a história, só recebem pioras genéricas); os eventos voltam para o último deles até a
primeira entrada nova. Datas nunca passam da data de
referência fixa do backend (`2026-10-23`).

## Rodando

O compose da raiz sobe o simulador como serviço próprio (imagem desta pasta), só depois
que o healthcheck do backend passa, falando com ele em `http://backend:5000`:

```bash
docker compose up --build -d          # na raiz: backend, front e simulador
docker compose logs -f simulador
docker compose stop simulador         # congela a fila sem derrubar o resto
```

Com o backend fora do Docker (`backend/.venv/bin/python backend/wsgi.py`), use o compose
avulso desta pasta, que fala com o host na porta 5000. Não rode os dois juntos.

```bash
cd simulador
docker compose up --build -d          # sobe o simulador avulso
docker compose logs -f simulador      # acompanha as entradas e os pulos
docker compose down                   # para

go run .                              # ou sem Docker
go run . -dump 3                      # só imprime 3 entradas e os eventos de cada uma, em JSON
```

| Variável | Padrão | |
|---|---|---|
| `BACKEND_URL` | `http://127.0.0.1:5000` (`http://backend:5000` no compose da raiz, `http://host.docker.internal:5000` no avulso) | |
| `HOSPITAL_ID` | `hsl` | |
| `ENTRY_INTERVAL` | `10s` | entre uma entrada e a próxima (duração do Go: `10s`, `1m`) |
| `EVENT_INTERVAL` | `5s` | entre eventos; o primeiro sai esse tempo depois da primeira entrada |
| `REFERENCE_DATE` | `2026-10-23` | a mesma do backend |
| `SIM_SEED` | relógio | semente fixa repete a mesma sequência |

O backend guarda o que o simulador manda só em memória: reiniciar o backend volta a fila
ao dataset original. Se isso acontecer com o simulador rodando, os eventos para pacientes
que sumiram voltam 404, ele os descarta e segue com as próximas entradas.

## Testes

```bash
cd simulador && go test ./...         # unitários: catálogo, gerador, roster, cliente HTTP, laço
go test -race -cover ./...
```

O build da imagem roda os testes antes de compilar. Do lado do backend,
`backend/tests/test_ingestao.py::test_dados_do_simulador_passam_na_ingestao_e_pulam_na_fila`
(marcado `lento`, pulado sem Go instalado) roda `go run . -dump 27` (27 entradas, cada uma com
os 2 eventos que recebe no ritmo padrão) e manda tudo para a app real: toda linha precisa
ser aceita, e todo paciente precisa subir pelo menos metade do caminho até o topo só com
esses dois eventos.
