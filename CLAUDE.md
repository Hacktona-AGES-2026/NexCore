# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## O que é o projeto

Desafio 1 da 9ª Hackatona de Engenharia de Software (PUCRS · Fin-x · Hospital São Lucas):
**priorização inteligente da fila cirúrgica**. Duas camadas existem hoje — normalização do
dataset (`backend/dataset/`) e um backend Flask que serve os CSVs normalizados ao frontend
por **WebSocket** (`backend/app/`). O algoritmo de priorização e o entregável
`fila_priorizada.csv` **ainda não existem**: a ação `queue.prioritize` que está no canal é
o encaixe do transporte, declarado `provisional`.

Dados 100% sintéticos. Documentos de contexto: [ANALISE_DADOS.md](ANALISE_DADOS.md),
[TESTES.md](TESTES.md), [backend/README.md](backend/README.md),
[backend/dataset/README.md](backend/dataset/README.md),
[backend/dataset/dicionario_dados.md](backend/dataset/dicionario_dados.md).

## Layout: `dataset/` vive dentro de `backend/`

O commit `2b598a1 chore: organizing folders` moveu `dataset/` para `backend/dataset/`.
Os caminhos reais hoje:

```
NexCore/
├── pytest.ini               configuração da suíte única (rode pytest daqui)
├── TESTES.md  ANALISE_DADOS.md
└── backend/
    ├── .venv/               venv do projeto inteiro (backend + pandas do dataset)
    ├── wsgi.py              carrega .env e cria a app
    ├── app/                 API Flask
    └── dataset/             CSVs de origem, normalizador, verificador oficial, tests/
        ├── normalizado/     CSVs versionados que o backend lê
        └── referencias/swalis.csv
```

Os dois arquivos que apontavam para o lugar antigo já foram corrigidos — era isso que
quebrava a suíte inteira (`DatasetUnavailable`) e a criação da app:

- `backend/app/config.py` — `BACKEND_ROOT = Path(__file__).resolve().parents[1]` (= `backend/`),
  base do `DATASET_DIR` padrão. Era `PROJECT_ROOT = parents[2]`, que caía na raiz do repo.
- `pytest.ini` — `testpaths`/`pythonpath` citam `backend/dataset/...`.

`backend/tests/test_layout_projeto.py` trava esse layout: se `dataset/` sair de dentro de
`backend/` sem os dois ajustes, ele falha com a mensagem apontando o caminho ausente, em vez
de 57 erros de `DatasetUnavailable`.

## Comandos

```bash
# testes — sempre da raiz do repositório (pytest.ini está aqui)
backend/.venv/bin/python -m pytest                      # 367 testes, ~25s
backend/.venv/bin/python -m pytest -m "not lento"       # 343 testes, ~13s
backend/.venv/bin/python -m pytest -m lento             # 24 testes, ~11s
backend/.venv/bin/python -m pytest backend/tests -q     # só o backend (327)
backend/.venv/bin/python -m pytest backend/tests/test_repositorio.py::test_filtro_por_especialidade_normalizada
backend/.venv/bin/python -m pytest -k "sem_urgencia"    # um recorte por nome

# subir o backend (HTTP + canal WebSocket)
backend/.venv/bin/python backend/wsgi.py                # http://127.0.0.1:5000 · ws://.../ws
# em produção o worker PRECISA ser de thread (o socket fica aberto):
#   gunicorn -k gthread -w 1 --threads 50 -b 0.0.0.0:5000 wsgi:app   # 1 processo: estado em memória

# tudo em Docker (da raiz): front em :8080 (nginx faz proxy de /v1 e /api), backend em :5000,
# e o simulador (imagem própria) só depois do healthcheck do backend
docker compose up --build -d
docker compose logs -f backend
docker compose logs -f simulador
docker compose stop simulador                           # congela a fila
docker compose down

# falar com o canal à mão (não precisa de front nem de dependência nova)
cd backend && .venv/bin/python tools/ws_client.py                  # interativo
cd backend && .venv/bin/python tools/ws_client.py queue.list size=3 oncological=true
cd backend && .venv/bin/python tools/ws_client.py stats.summary --raw | jq .payload

# simulador avulso, só com o backend FORA do Docker (senão seriam dois simuladores)
cd simulador && docker compose up --build -d && docker compose logs -f simulador
cd simulador && go test ./...

# regenerar backend/dataset/normalizado/ a partir dos CSVs de origem
backend/.venv/bin/python backend/dataset/normalizar_dataset.py

# verificador oficial do entregável (--dataset aponta para os CSVs DE ORIGEM)
backend/.venv/bin/python backend/dataset/verificar_fila_priorizada.py \
    <fila_priorizada.csv> [--dataset backend/dataset/]

# instalar dependências (requirements-dev puxa requirements.txt + o pandas do dataset)
backend/.venv/bin/pip install -r backend/requirements-dev.txt
```

`pytest.ini` põe `backend/` e `backend/dataset/` no `pythonpath`, então `from app import ...`
e `import normalizar_dataset` funcionam de qualquer diretório. Os testes marcados `lento`
chamam o verificador oficial por subprocess (um import de pandas por caso) — é daí que vem
quase todo o tempo da suíte.

`TESTES.md` está no `.gitignore` da raiz: ele é referenciado pelos docs mas não é versionado.

## Arquitetura

**Pipeline de dados.** `backend/dataset/*.csv` (origem, dos organizadores, nunca alterados) →
`normalizar_dataset.py` → `backend/dataset/normalizado/*_normalizad*.csv` +
`analise_qualidade.json`. A normalização **preserva todas as linhas**: nada é removido nem
imputado, e os problemas conhecidos (flags divergentes do CID, pares paciente/procedimento
repetidos, eventos órfãos) ganham colunas `*_norm` e sinalizadores em vez de correção
silenciosa. Os CSVs normalizados são versionados; o script redireciona `BASE`/`OUT` por
monkeypatch nos testes, então rodar a suíte nunca os sobrescreve.

**Backend.** Fábrica em `backend/app/__init__.py` (`create_app(environment, **overrides)`);
`get_config` escolhe entre os ambientes `desenvolvimento` / `teste` / `producao`.
`app/data/reader.py` lê os quatro CSVs e converte tipos (int, float, date, bool, acentos);
`app/data/repository.py` monta índices por id em memória na criação da app
(`data.init_app` guarda a instância em `app.extensions["repository"]`, lida via
`current_repository()`). São menos de mil solicitações — sem banco, sem pandas no backend.
`app/errors.py` define `RequestError` (message/status/details), usado pelo HTTP e pelo canal,
e garante que todo erro HTTP sai como JSON, inclusive 500 e 404 do Werkzeug. Trocar a fonte
de dados é só ajustar `DATASET_DIR`.

**O transporte é WebSocket** (`flask-sock`, pinado em `requirements.txt`). Quatro camadas em
`app/realtime/`, em ordem de dependência: `protocol.py` (formato dos frames) → `params.py`
(validação dos params de um comando) → `actions.py` + `handlers.py` (os cálculos) →
`channel.py` (o laço da conexão). As três primeiras são **puras**: sem Flask, sem socket.
`channel.serve(ws, repository, limits, logger)` recebe o socket como argumento e só chama
`receive()`/`send()`, então os testes passam um duplo. `realtime/__init__.py` registra a rota
em `WS_PATH` (padrão `/ws`) e checa `Origin` contra `CORS_ORIGINS` — o handshake WebSocket
não passa por CORS, essa checagem é nossa. Servir de verdade exige worker de thread:
`gunicorn -k gthread --threads 50`, nunca o `sync`.

**API da regulação (`app/regulation/`)** é o que o front consome: REST em
`/v1/hospitais/<HOSPITAL_ID>/...` (camelCase, erros `{"detail"}` em português) e o WebSocket
`/v1/ws`, que só envia (`queue.snapshot` ao conectar, depois `queue.patch`/`audit.appended`/
`pendency.resolved`/`activity` via `hub.Hub`). `state.QueueState` guarda a fila mutável em
memória sob um lock — por isso **um processo só**. A regra fica em `app/prioritization/`
(pura); a regra de ouro usa o "sem urgência clínica" do verificador, não "classe D".
`/painel/impacto` roda o verificador oficial por subprocess (`regulation/verifier.py`) na fila
do Neco e na fila manual, com cache por ordem; `/fila/exportar` é o `fila_priorizada.csv` da fila
atual. Ingestão: `/fila/entradas` e `/fila/eventos` recebem linhas dos CSVs de origem
(objeto ou lote), `regulation/intake.py` valida e normaliza como o normalizador, e o
`QueueState` encaixa (`prioritization.place`, menos inversões + regra de ouro) e empurra os
frames; quem a regulação travou não é movido. As linhas ingeridas vão ao verificador como
`extra` (cópia dos CSVs de origem com as linhas no fim), senão ele acusaria id inexistente.
O que entra pela ingestão vive só em memória, como o resto do estado: reiniciar o backend
volta ao dataset.

**Simulador (`simulador/`, Go, imagem própria)** sobe no compose da raiz depois do
healthcheck do backend (`test_docker_compose.py` trava isso; `simulador/docker-compose.yml` é
o avulso, para backend fora do Docker) e alimenta a ingestão na demonstração como um timer:
uma entrada nova a cada 10 s (`ENTRY_INTERVAL`) e, desde a primeira, um evento a cada 5 s
(`EVENT_INTERVAL`) na **última** entrada (`SOL-2026-9NNNN`). Quando os dois coincidem o evento
sai antes, então cada entrada recebe 2 eventos e os 2 primeiros passos de cada história
carregam o pulo na fila. `go test ./...` lá dentro; o contrato com o backend é
`test_ingestao.py::test_dados_do_simulador_passam_na_ingestao_e_pulam_na_fila`.

**CI/CD** (`.github/workflows/ci-cd.yml`, guia em `docs/DEPLOY.md`): testes Go e Python em
todo push/PR; push na `main` com os dois verdes faz deploy na VPS da Hostinger pela
`hostinger/deploy-action` (secrets `HOSTINGER_API_KEY`, `HOSTINGER_VM_ID`, `GEMINI_API_KEY`).

**Além disso, HTTP tem `/api/health`** (mais `GET /`, que anuncia o canal, o protocolo e as
ações). O blueprint `api` continua existindo para ele: um healthcheck de deploy não deve
precisar abrir socket.

**Superfície do canal.** O cliente manda `{id, action, params}`; o servidor responde com
frames que sempre têm `type`: `welcome` (ao conectar), `progress`, `result`, `error`. O `id`
é opaco e volta em todos os frames do comando, o que é como o cliente liga o progresso de um
cálculo à chamada que o disparou. Ações: `queue.list`, `queue.request`, `queue.events`,
`patient.events`, `queue.prioritize`, `catalog.procedures`, `catalog.swalis`,
`catalog.filters`, `stats.summary`. Listagens devolvem
`payload = {"data": [...], "pagination": {page, size, total, pages}}`. Filtros de
`queue.list` (`params.queue_filters`): `specialty`, `priority`, `city`, `procedure_id`,
`oncological`, `min_days`, `max_days`, `min_age`, `search`, mais
`page`/`size`/`sort_by`/`order`. Como o comando é JSON, `oncological` aceita booleano de
verdade além das formas em texto.

**Cálculo longo reporta progresso.** Uma ação é uma função de
`(repository, params, limits)` que devolve o payload; uma ação longa é um **gerador** que
emite `Progress(completed, total, label)` e termina com `return payload`. `actions.run`
traduz isso em frames; o cálculo nunca vê um socket. Registrar é um decorator
(`@action("nome")`), e o transporte não muda. Um comando inválido rende um frame `error` e
**não** fecha a conexão: pode haver cálculo em andamento nela.

**Teste do backend contra dataset sintético.** `backend/tests/conftest.py` expõe
`dataset_sintetico`/`app_sintetico`, que escrevem CSVs com o mesmo cabeçalho do dataset real
em `tmp_path` e criam uma app apontada para lá. Use isso para asserções exatas
(`== ["SOL-B", "SOL-A", "SOL-C"]`); os testes contra o dataset real
(`test_websocket.py`, `test_contrato_dataset.py`) travam de propósito os números conhecidos —
941 solicitações, 1.505 eventos, 177 oncológicas por CID, 44 flags divergentes, 22 pares
repetidos, 9 eventos órfãos, 353 esperas acima de 365 dias. Se o normalizador mudar e um
desses números sair do lugar, a suíte quebra: é o ponto. `backend/dataset/tests/conftest.py`
tem o par para os scripts (`mini_dataset`, `fabrica_fila`, `fabrica_evento`), montando os
CSVs **de origem** em `tmp_path`.

**Cliente de terminal.** `backend/tools/ws_client.py` conversa com o canal sem front:
modo interativo, ou `ws_client.py <ação> chave=valor ...`. Os pares viram JSON de verdade
(`size=3` número, `oncological=true` booleano). `--raw` imprime um frame de JSON por linha
para o `jq`, e o processo sai com 1 se o comando acabou em `error`. É ferramenta de
desenvolvimento, fora da app servida; as partes puras (`parse_params`, `describe`,
`summarize`) têm testes em `test_ws_client.py`.

**Teste do canal.** `conftest.py` tem `WsFalso` (duplo do socket: entrega comandos de uma
lista, guarda os frames) e as fixtures `conversa` (roda uma conversa inteira) e `pedir`
(atalho para uma ação → payload). Use-as para tudo; `test_websocket_integracao.py` sobe o
servidor numa porta efêmera com um cliente real só para o que o duplo não prova — rota
registrada, handshake, frames saindo durante o cálculo, `Origin` recusada.

## Convenções que a suíte protege

**Fronteira de idioma.** Tudo que é nosso é inglês: código, nomes de ação, parâmetros,
chaves de envelope (`data`, `pagination`, `payload`, `error`), nomes de função. Tudo que é do dataset fica como
está, em português: nomes de coluna (`solicitacao_id`, `dias_em_fila`, `oncologico_cid`) e
valores de domínio (`alta`, `media`, `baixa`). Logo `sort_by: "dias_em_fila"` e
`priority: "alta"` são o esperado. Nomes de teste e docs seguem em português. `test_repositorio.py` monta
fixtures com colunas em português e consulta com filtros em inglês justamente para quebrar
se alguém renomear um lado sem o outro — um replace automático já trocou `media` por `mean`
numa fixture.

**Oncologia vem do CID, não da flag.** `oncologico_cid` é derivado do prefixo `C` em
`cid_principal_norm`. A flag manual permanece exposta como `flag_oncologico_norm` só para
auditoria; elas divergem em 44 das 941 linhas, e a regra de ouro depende do CID.

**Nada é imputado.** Campo vazio no CSV vira `null` no JSON. Ausência de ASA ou de dor não
é zero.

**Nenhuma mensagem de erro interna vaza.** Uma exceção inesperada vira `internal server
error` com status 500, no HTTP e no canal, com o traceback só no log. `test_http.py` e
`test_websocket_erros.py` conferem que o texto original não aparece na resposta.

**Data de referência fixa** em `2026-10-23` (`REFERENCE_DATE`). `dias_em_fila` vem do CSV;
não recalcule contra a data de hoje.

**O verificador oficial é caixa-preta.** `backend/dataset/verificar_fila_priorizada.py` veio
dos organizadores: não edite e não importe. Os testes o chamam por subprocess com `--dataset`
apontado para uma fila sintética e conferem código de saída e texto. Atenção: ele lê os CSVs
**de origem** (`fila_cirurgica.csv`, `eventos_clinicos.csv`), não os normalizados, e o default
de `--dataset` é a pasta do próprio script. Ele sai com 1 em erro (coluna obrigatória ausente,
posição repetida ou não inteira, id inexistente, regra de ouro violada) e com 0 em aviso
(justificativa vazia, cobertura incompleta, oncológico fora do arquivo).

**Regra de ouro.** Nenhum paciente com CID iniciado por `C` pode ficar abaixo de um paciente
"sem urgência clínica" — definição conservadora no cabeçalho do verificador (não oncológico,
EVA ≤ 3, limitação nenhuma/leve, sem CID de obstrução/instabilidade, sem PS/internação/
biópsia positiva/progressão/piora nos eventos, sem palavra de alarme na justificativa).

**`.env` não é versionado**, e `backend/wsgi.py` chama `load_dotenv` *antes* de importar
`app`, porque `Config` lê `os.environ` no corpo da classe. `test_env.py` confere os nomes
de chave contra `.env.example`, que é versionado. Cuidado: `test_config.py::test_dataset_dir_vem_do_ambiente`
dá `importlib.reload` no módulo de config — se o default de `DATASET_DIR` estiver errado, o
reload contamina os testes seguintes da sessão.

## Quando o algoritmo de priorização entrar

O encaixe já existe: a ação `queue.prioritize` em `app/realtime/handlers.py`. Hoje ela
ordena por `dias_em_fila` e nada mais, se declara com `strategy="placeholder:dias_em_fila"`
e `provisional=True`, **ignora a regra de ouro** e não passaria pelo verificador. Ela está
lá para o front integrar contra um contrato estável — não a confunda com a regra, e não
remova os campos que a denunciam sem que a regra real tenha entrado.

O lugar da regra é `backend/app/prioritization/`, em **função pura** (recebe fila +
eventos, devolve posição + justificativa), chamada de dentro de `handlers.prioritize`. O
contrato do cliente não muda: mesma ação, mesmos frames, mesmas chaves `solicitacao_id` /
`posicao` / `justificativa` que o entregável pede. Se o cálculo for caro, emita
`Progress(...)` e o progresso chega ao front sem nenhuma mudança no transporte.

O entregável é `fila_priorizada.csv` com `solicitacao_id`, `posicao`, `justificativa`, uma
linha por solicitação considerada ativa, e precisa passar pelo verificador antes de
entregar.
