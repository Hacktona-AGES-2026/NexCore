# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## O que é o projeto

Desafio 1 da 9ª Hackatona de Engenharia de Software (PUCRS · Fin-x · Hospital São Lucas):
**priorização inteligente da fila cirúrgica**. O "Neco" é o assistente que ordena a fila e
explica cada posição. Peças:

- `backend/dataset/` — CSVs de origem, normalizador, verificador oficial.
- `backend/app/` — Flask: regra de priorização (`prioritization/`), API da regulação que o
  front consome (`regulation/`), canal WebSocket de comandos (`realtime/`), textos por IA
  (`neco_ia/`).
- `frontend/` — React + TypeScript + Vite (painel da regulação, telão).
- `simulador/` — Go, só biblioteca padrão; alimenta a ingestão na demonstração.
- `docs/` — `CONTRATO_BACKEND.md` (contrato front↔back), `DPSS.md`, `ANALISE_DADOS.md`. `docs/TESTES.md` existe localmente mas está no `.gitignore`.
- `mock/` — mockups HTML estáticos, não fazem parte da app.

Dados 100% sintéticos. Ver também [backend/README.md](backend/README.md),
[frontend/README.md](frontend/README.md), [backend/dataset/README.md](backend/dataset/README.md),
[backend/dataset/dicionario_dados.md](backend/dataset/dicionario_dados.md).

## Comandos

```bash
# ambiente Python (venv único para backend + pandas do dataset; não versionado)
python3.12 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements-dev.txt

# testes — sempre da raiz do repositório (pytest.ini está aqui)
backend/.venv/bin/python -m pytest
backend/.venv/bin/python -m pytest -m "not lento"       # pula o verificador oficial por subprocess
backend/.venv/bin/python -m pytest backend/tests -q     # só o backend
backend/.venv/bin/python -m pytest backend/tests/test_repositorio.py::test_filtro_por_especialidade_normalizada
backend/.venv/bin/python -m pytest -k "sem_urgencia"

# subir o backend (HTTP + WebSockets)
backend/.venv/bin/python backend/wsgi.py                # http://127.0.0.1:5000
# produção: worker de thread e UM processo (estado em memória, socket aberto)
#   gunicorn -k gthread -w 1 --threads 50 -b 0.0.0.0:5000 wsgi:app

# frontend
cd frontend && npm install
cd frontend && npm run dev            # :5173, backend simulado (src/mock), sem servidor
cd frontend && npm run dev:backend    # usa frontend/.env.backend → backend real
cd frontend && npm run typecheck      # tsc -b; npm run build faz typecheck + vite build

# simulador
cd simulador && go test ./...         # o CI também roda gofmt -l, go vet e go test -race

# tudo em Docker (da raiz): front em :8080 (nginx faz proxy de /v1 e /api), backend em :5000,
# simulador só depois do healthcheck do backend
docker compose up --build -d
docker compose logs -f backend
docker compose stop simulador                           # congela a fila
docker compose down
# simulador avulso só com o backend FORA do Docker (senão seriam dois)
cd simulador && docker compose up --build -d

# falar com o canal de comandos à mão
cd backend && .venv/bin/python tools/ws_client.py                  # interativo
cd backend && .venv/bin/python tools/ws_client.py queue.list size=3 oncological=true
cd backend && .venv/bin/python tools/ws_client.py stats.summary --raw | jq .payload

# regenerar backend/dataset/normalizado/ a partir dos CSVs de origem
backend/.venv/bin/python backend/dataset/normalizar_dataset.py

# verificador oficial do entregável (--dataset aponta para os CSVs DE ORIGEM)
backend/.venv/bin/python backend/dataset/verificar_fila_priorizada.py \
    <fila_priorizada.csv> [--dataset backend/dataset/]
```

`pytest.ini` põe `backend/` e `backend/dataset/` no `pythonpath`, então `from app import ...`,
`import normalizar_dataset` e `from dataset.normalizar_dataset import ...` funcionam de
qualquer diretório. Os testes marcados `lento` chamam o verificador oficial por subprocess
(um import de pandas por caso): é daí que vem quase todo o tempo da suíte.
`test_docker_compose.py` precisa de Docker; o teste de contrato com o simulador roda
`go run . -dump` e é pulado sem Go.

## Layout: `dataset/` vive dentro de `backend/`

`backend/app/config.py` usa `BACKEND_ROOT = Path(__file__).resolve().parents[1]` como base de
`DATASET_DIR` (normalizados, que o repositório lê) e `VERIFIER_DATASET_DIR` (origem, que o
verificador e a ingestão usam). `pytest.ini` cita `backend/dataset/...`.
`backend/tests/test_layout_projeto.py` trava isso: mover `dataset/` sem ajustar os dois dá uma
falha clara em vez de dezenas de `DatasetUnavailable`.

## Arquitetura

**Pipeline de dados.** `backend/dataset/*.csv` (origem, dos organizadores) →
`normalizar_dataset.py` → `backend/dataset/normalizado/*_normalizad*.csv` +
`analise_qualidade.json`. A normalização **preserva todas as linhas**: nada é removido nem
imputado, e os problemas conhecidos (flags divergentes do CID, pares paciente/procedimento
repetidos, eventos órfãos) ganham colunas `*_norm` e sinalizadores. Os CSVs normalizados são
versionados; os testes redirecionam `BASE`/`OUT` por monkeypatch, então a suíte não os
sobrescreve.

**Backend.** Fábrica em `backend/app/__init__.py` (`create_app(environment, **overrides)`);
ambientes `desenvolvimento` / `teste` / `producao`. `app/data/reader.py` lê os CSVs e converte
tipos; `app/data/repository.py` monta índices em memória (`app.extensions["repository"]`, lido
via `current_repository()`). Menos de mil solicitações: sem banco, sem pandas no caminho de
leitura. `app/errors.py` define `RequestError` (message/status/details) e garante que todo erro
HTTP sai como JSON.

**Priorização (`app/prioritization/`, funções puras, sem Flask nem socket).** Dois motores:

- **DPS** (`dps.py`): `P = (t / M) * (1 + c)`, com SWALIS e eventos. Pesos são protótipo
  (`provisional-equal-v1`, não PAPRIKA). Roda por `pipeline.PrioritizationPipeline` (passos
  componíveis `DpsStep` → `DpssStep`).
- **DPSS** (`dpss.py`, `MODEL_VERSION = "0.2.0-experimental"`): `DPS` com o termo
  socioeconômico `w*S` (EVFAM-BR / INSE municipal / distância, com fallbacks marcados) e
  `disability_weight`. Detalhes e terminologia (não chamar de DALY) em `docs/DPSS.md`.

A fila da regulação é a leitura do Neco ordenada por `ranking.rank`: banda de segurança
(A1/A2 e oncológicos) primeiro, depois o score DPSS, empate pela ordem do dataset; posições
travadas por humanos ficam onde foram postas. `ranking.golden_rule_violation` confere a regra
de ouro, que usa o "sem urgência clínica" do verificador, não "classe D".

**API da regulação (`app/regulation/`)** é o que o front consome: REST em
`/v1/hospitais/<HOSPITAL_ID>/...` (camelCase, erros `{"detail"}` em português) e o WebSocket
`/v1/ws`, que **só envia**: `queue.snapshot` ao conectar, depois `queue.patch` /
`audit.appended` / `pendency.resolved` / `activity` via `hub.Hub`. As ações do usuário vão por
REST. `state.QueueState` guarda a fila mutável em memória sob um lock, por isso **um processo
só**. `/painel/impacto` roda o verificador oficial por subprocess (`regulation/verifier.py`) na
fila do Neco e na manual, com cache por ordem; `/fila/exportar` devolve o `fila_priorizada.csv`
da fila atual. Ingestão REST: `/fila/entradas` e `/fila/eventos` recebem linhas dos CSVs de
origem (objeto ou lote atômico); `regulation/intake.py` valida e normaliza como o normalizador,
e `QueueState` encaixa (`prioritization.place`) sem mover quem a regulação travou. Isso vive
**só em memória**: reiniciar volta ao dataset. As linhas ingeridas vão ao verificador como
`extra` (cópia dos CSVs de origem com elas no fim). O contrato completo, com os tipos do front
como fonte da verdade (`frontend/src/api/types.ts`), está em `docs/CONTRATO_BACKEND.md`.

**Neco por IA (`app/neco_ia/`).** Explicações, comentários de painel e "Pergunte ao Neco" via
Gemini (variáveis em `backend/.env.example`). Sem chave ou com `NECO_IA_ENABLED=false`, tudo
cai nos textos por regras: app, testes e demo funcionam offline. O Neco explica, mas não altera
posições.

**Canal de comandos (`app/realtime/`, rota `WS_PATH`, padrão `/ws`).** Separado do `/v1/ws`.
Camadas em ordem de dependência: `protocol.py` (frames) → `params.py` (validação) →
`actions.py` + ações → `channel.py` (laço da conexão). As três primeiras são puras;
`channel.serve(ws, repository, limits, logger)` recebe o socket como argumento, então os
testes passam um duplo. `realtime/__init__.py` registra a rota e checa `Origin` contra
`CORS_ORIGINS` (o handshake WebSocket não passa por CORS). As ações se registram por import,
em `realtime/__init__.py`:

- `handlers.py`: `queue.list`, `queue.request`, `queue.events`, `patient.events`,
  `catalog.procedures`, `catalog.swalis`, `catalog.filters`, `stats.summary`.
- `prioritization.py`: `queue.prioritize` roda o pipeline DPS e devolve `strategy: "dps"`,
  `provisional: True` e o bloco `model` com `clinical_use_authorized: False`. Não remova
  essas marcas enquanto os pesos não forem validados.
- `dpss.py`: `queue.prioritize.dpss` é o opt-in experimental. Não substitui `queue.prioritize`.
- `ingestion.py`: `queue.request.create`, `clinical_event.create`, `procedure.upsert`,
  servidas por `data/ingestion.py`, com recálculo reativo do DPSS em `realtime/dpss_live.py`.
  Em testes, aponte `DATASET_DIR` e `VERIFIER_DATASET_DIR` para `tmp_path`.

Frames: o cliente manda `{id, action, params}`; o servidor responde com `type` em `welcome`,
`progress`, `result` e `error`, e o `id` volta em todos. Listagens devolvem
`payload = {"data": [...], "pagination": {page, size, total, pages}}`. Uma ação é
`(repository, params, limits) -> payload`; uma ação longa é um **gerador** que emite
`Progress(completed, total, label)` e termina com `return payload`, e `actions.run` traduz isso
em frames. Comando inválido rende `error` e **não** fecha a conexão.

**Frontend.** `src/api/` (tipos + cliente HTTP/WS), `src/mock/` (backend em memória, a
implementação de referência do contrato), `src/domain/` (regras puras, espelho das do
backend), `src/state/QueueContext`. Por padrão usa o mock (`VITE_USE_MOCK=true`); variáveis em
`frontend/.env.example`. Se `/painel/impacto` ou `/fila/exportar` derem 404, o front cai em
`src/mock/impacto.json`. Em Docker, o nginx (`nginx.conf.template`, `BACKEND_UPSTREAM`) serve o
build e faz proxy de `/v1` e `/api`, então o navegador fala com uma origem só.

**Simulador (`simulador/`).** Sobe no compose da raiz depois do healthcheck do backend
(`test_docker_compose.py` trava isso). Uma entrada nova a cada 10 s (`ENTRY_INTERVAL`) e, desde
a primeira, um evento a cada 5 s (`EVENT_INTERVAL`) na **última** entrada (`SOL-2026-9NNNN`).
Quando os dois coincidem, o evento sai antes. O contrato com o backend é
`test_ingestao.py::test_dados_do_simulador_passam_na_ingestao_e_pulam_na_fila`.

**CI** (`.github/workflows/`): Go (gofmt, vet, `test -race`) e pytest em todo push/PR. Rode
os dois localmente antes de subir. HTTP também expõe `/api/health` (healthcheck sem socket) e
`GET /`, que anuncia o canal e as ações.

## Testes

`backend/tests/conftest.py` expõe `dataset_sintetico`/`app_sintetico` (CSVs com o cabeçalho
real em `tmp_path`) para asserções exatas; `WsFalso` (duplo do socket) e as fixtures `conversa`
e `pedir` para o canal. `test_websocket_integracao.py` sobe um servidor real numa porta efêmera
só para o que o duplo não prova (rota, handshake, frames durante o cálculo, `Origin` recusada).
`backend/dataset/tests/conftest.py` tem `mini_dataset`, `fabrica_fila` e `fabrica_evento`, que
montam CSVs **de origem**.

Os testes contra o dataset real (`test_websocket.py`, `test_contrato_dataset.py`) travam de
propósito os números conhecidos: 941 solicitações, 1.505 eventos, 177 oncológicas por CID, 44
flags divergentes, 22 pares repetidos, 9 eventos órfãos e 353 esperas acima de 365 dias. Se o
normalizador mudar e um número sair do lugar, a suíte quebra, e é para isso que eles existem.

## Convenções que a suíte protege

**Fronteira de idioma.** Tudo que é nosso é inglês: código, nomes de ação, parâmetros, chaves
de envelope (`data`, `pagination`, `payload`, `error`). Tudo que é do dataset fica em
português: colunas (`solicitacao_id`, `dias_em_fila`, `oncologico_cid`) e valores de domínio
(`alta`, `media`, `baixa`). Logo `sort_by: "dias_em_fila"` e `priority: "alta"`. Nomes de teste
e docs em português. A API da regulação (`/v1`) é a exceção: chaves em camelCase e `detail` em
português, porque segue `frontend/src/api/types.ts`. `test_repositorio.py` mistura colunas em
português com filtros em inglês justamente para quebrar se alguém renomear um lado só (um
replace automático já trocou `media` por `mean`).

**Oncologia vem do CID, não da flag.** `oncologico_cid` = prefixo `C` em `cid_principal_norm`.
`flag_oncologico_norm` fica exposta só para auditoria (divergem em 44 de 941).

**Nada é imputado.** Vazio no CSV vira `null`. Ausência de ASA ou de dor não é zero. No DPSS,
todo fallback (INSE, 0.5) é marcado na proveniência.

**Nenhuma mensagem de erro interna vaza.** Exceção inesperada vira `internal server error` 500,
no HTTP e no canal, com o traceback só no log (`test_http.py`, `test_websocket_erros.py`).

**Data de referência fixa** em `2026-10-23` (`REFERENCE_DATE`). `dias_em_fila` vem do CSV; não
recalcule contra hoje.

**O verificador oficial é caixa-preta.** `backend/dataset/verificar_fila_priorizada.py` veio dos
organizadores: não edite e não importe, chame por subprocess. Ele lê os CSVs **de origem**
(`fila_cirurgica.csv`, `eventos_clinicos.csv`), e o default de `--dataset` é a pasta do próprio
script. Sai com 1 em erro (coluna ausente, posição repetida/não inteira, id inexistente, regra
de ouro violada) e com 0 em aviso (justificativa vazia, cobertura incompleta, oncológico fora).

**Regra de ouro.** Nenhum paciente com CID iniciado por `C` abaixo de um paciente "sem urgência
clínica", na definição conservadora do cabeçalho do verificador (não oncológico, EVA ≤ 3,
limitação nenhuma/leve, sem CID de obstrução/instabilidade, sem PS/internação/biópsia
positiva/progressão/piora nos eventos, sem palavra de alarme na justificativa). Reordenação
manual que a viola recebe 422.

**Entregável.** `fila_priorizada.csv` com `solicitacao_id`, `posicao`, `justificativa`, uma
linha por solicitação ativa (é o que `/fila/exportar` gera), e precisa passar pelo verificador.

**`.env` não é versionado.** `backend/wsgi.py` chama `load_dotenv` *antes* de importar `app`,
porque `Config` lê `os.environ` no corpo da classe. `test_env.py` confere as chaves contra
`.env.example`, que é versionado: variável nova em `Config` precisa entrar lá.
`test_config.py::test_dataset_dir_vem_do_ambiente` dá `importlib.reload` no config, então um
default errado de `DATASET_DIR` contamina os testes seguintes da sessão.
