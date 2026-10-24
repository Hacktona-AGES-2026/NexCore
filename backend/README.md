# Backend — NexCore

API Flask sobre a fila cirúrgica do Desafio 1 (9ª Hackatona · PUCRS/Fin-x/Hospital São Lucas).
Serve a fila, os eventos clínicos e o catálogo de procedimentos para o frontend e para os
experimentos de priorização. **Dados 100% sintéticos.**

## Rodar

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env           # e troque a SECRET_KEY
python wsgi.py                 # http://127.0.0.1:5000
```

Alternativas: `flask --app wsgi run --debug` em desenvolvimento,
`gunicorn -w 2 -b 0.0.0.0:5000 wsgi:app` para servir de verdade.

```bash
pytest -q                      # testes do backend
```

A suíte do projeto inteiro (backend + scripts de dataset) roda da raiz do repositório;
veja [TESTES.md](../TESTES.md).

## Estrutura

```
backend/
├── wsgi.py                  ponto de entrada (create_app)
├── app/
│   ├── __init__.py          fábrica da aplicação, rota raiz, CORS
│   ├── config.py            configuração por ambiente/variáveis
│   ├── errors.py            handlers que devolvem JSON em vez de HTML
│   ├── data/
│   │   ├── reader.py        leitura dos CSVs e conversão de tipos
│   │   └── repository.py    índices em memória, filtros e agregações
│   └── api/
│       ├── params.py        validação de query string e paginação
│       ├── queue.py         /fila, /fila/<id>, eventos
│       ├── catalog.py       procedimentos e referências
│       └── health.py        /saude e /estatisticas
└── tests/                  leitor, repositório, API, config e contrato
```

A fonte de dados é `dataset/normalizado/` (gerada por `dataset/normalizar_dataset.py`).
São menos de mil solicitações, então os quatro CSVs são carregados uma vez na criação da
aplicação e servidos a partir de dicionários por id — sem banco e sem pandas. Trocar o
diretório é só ajustar `DATASET_DIR`; se ele não existir, a aplicação falha na subida com
uma mensagem dizendo o que rodar.

## Endpoints

| Método | Rota | O que faz |
|---|---|---|
| GET | `/` | Nome do serviço e lista de rotas registradas |
| GET | `/api/saude` | Status, data de referência e contagem de cada tabela |
| GET | `/api/estatisticas` | Agregados da fila: espera, prioridades, especialidades, eventos |
| GET | `/api/fila` | Fila paginada, com filtros e ordenação |
| GET | `/api/fila/<solicitacao_id>` | Solicitação + procedimento + eventos ligados |
| GET | `/api/fila/<solicitacao_id>/eventos` | Eventos da solicitação, em ordem cronológica |
| GET | `/api/pacientes/<paciente_id>/eventos` | Eventos do paciente (inclui outras solicitações) |
| GET | `/api/procedimentos` | Catálogo com porte, risco, duração e UTI |
| GET | `/api/referencias/swalis` | As 5 classes SWALIS com prazo máximo |
| GET | `/api/referencias/filtros` | Valores aceitos em `especialidade`, `prioridade` e `ordenar_por` |

### Parâmetros de `/api/fila`

`especialidade`, `prioridade` (`alta`/`media`/`baixa`), `municipio`, `procedimento_id`,
`oncologico` (`sim`/`nao`, derivado do CID), `dias_minimo`, `dias_maximo`, `idade_minima`,
`busca` (id, nome, procedimento, CID, justificativa e observações — ignora acento e caixa),
`ordenar_por` (padrão `dias_em_fila`), `ordem` (`desc`/`asc`), `pagina`, `tamanho`.

Texto com acento e caixa variada é aceito nos filtros: `especialidade=oftalmologia` e
`especialidade=Oftalmologia` dão o mesmo resultado.

```bash
curl "localhost:5000/api/fila?oncologico=sim&ordenar_por=dias_em_fila&tamanho=5"
curl "localhost:5000/api/fila?especialidade=ortopedia&dias_minimo=365"
curl "localhost:5000/api/fila/SOL-2025-00048"
```

Respostas de lista vêm como `{"dados": [...], "paginacao": {...}}`. Erros vêm como
`{"erro": {"mensagem": "...", "status": 400}}`, sempre em JSON.

## Decisões que afetam quem consome a API

- **Oncologia vem do CID, não da flag.** `oncologico_cid` é derivado do prefixo `C` em
  `cid_principal_norm`; a flag manual continua exposta como `flag_oncologico_norm` para
  auditoria. Elas divergem em 44 das 941 linhas, e a regra de ouro depende do CID.
- **Nada é imputado.** Campo vazio no CSV vira `null` no JSON. Ausência de ASA ou de dor
  não é zero e não é ausência de risco — quem consome decide como tratar.
- **Nenhuma linha é descartada.** As 22 solicitações com par paciente/procedimento repetido
  e os eventos órfãos continuam na resposta, sinalizados (`duplicata_conteudo`,
  `solicitacao_na_fila`). Remover é decisão de produto, não de transporte de dados.
- **A data de referência é fixa** em `2026-10-23` (`REFERENCE_DATE`), igual ao dataset.
  `dias_em_fila` vem do CSV; não recalcule contra a data de hoje.
- **O código é em inglês; a API não.** Identificadores, funções e módulos em inglês;
  rotas, parâmetros de query e chaves do JSON seguem os termos do dataset
  (`solicitacao_id`, `dias_em_fila`), para casar com `dataset/dicionario_dados.md`.
- **O `.env` é lido pelos dois modos de subir.** `wsgi.py` chama `load_dotenv` antes de
  importar `app`, porque `Config` lê `os.environ` no corpo da classe — carregar depois não
  teria efeito. Variável já exportada no shell vence o arquivo.
- **CORS liberado** (`CORS_ORIGINS=*`) para o frontend em desenvolvimento. Restrinja antes
  de qualquer exposição pública.

## Ainda não implementado

O **algoritmo de priorização** e o `fila_priorizada.csv` não estão aqui. Esta camada entrega
os dados limpos, consultáveis e com as inconsistências visíveis; escolher pesos, classes de
urgência e o formato da justificativa é a próxima etapa, e a regra de ouro precisa ser
verificada com `dataset/verificar_fila_priorizada.py` antes de entregar.

Quando entrar, o lugar natural é um módulo `app/prioritization/` com a regra em função pura
(recebe fila + eventos, devolve posição + justificativa) e uma rota `POST /api/priorizacao`
ou `GET /api/fila/priorizada`, para que a regra fique testável sem HTTP.
