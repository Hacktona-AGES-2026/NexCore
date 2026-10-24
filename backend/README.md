# Backend — NexCore

Backend Flask sobre a fila cirúrgica do Desafio 1 (9ª Hackatona · PUCRS/Fin-x/Hospital São
Lucas). O frontend consome tudo por **uma conexão WebSocket**: a fila, os eventos clínicos,
o catálogo e os cálculos — que reportam progresso enquanto rodam, em vez de deixar a tela
parada esperando a resposta. **Dados 100% sintéticos.**

HTTP sobrou só para `/api/health` e para a raiz, que anuncia o canal.

## Rodar

Do zero, num clone novo:

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt      # cobre o projeto inteiro, pandas incluso
cp .env.example .env                     # e troque a SECRET_KEY
python wsgi.py                           # http://127.0.0.1:5000 · ws://127.0.0.1:5000/ws
```

Não precisa gerar o dataset: `dataset/normalizado/` é versionado. Se ele não existir, a
aplicação falha na subida dizendo o que rodar (`python dataset/normalizar_dataset.py`).

Para servir de verdade, o worker **precisa ser de thread** — o processo fica parado numa
conexão aberta, e o worker `sync` padrão do gunicorn não dá conta:

```bash
gunicorn -k gthread -w 2 --threads 50 -b 0.0.0.0:5000 wsgi:app
```

Conferir que está tudo de pé — 270 testes, ~10s, **da raiz do repositório** (é lá que mora
o `pytest.ini`):

```bash
cd ..
backend/.venv/bin/python -m pytest             # tudo
backend/.venv/bin/python -m pytest -k websocket    # só o canal (83)
```

`requirements-dev.txt` puxa o pandas dos scripts de dataset, então uma venv serve a suíte
inteira (230 de backend + 40 de dataset). Se você instalar só `requirements.txt`, os de
dataset **pulam** — dois skips de módulo com a razão no relatório — em vez de interromper a
coleta. Detalhes em [TESTES.md](../TESTES.md).

## Estrutura

```
backend/
├── wsgi.py                  ponto de entrada (create_app)
├── app/
│   ├── __init__.py          fábrica da aplicação, rota raiz, CORS
│   ├── config.py            configuração por ambiente/variáveis
│   ├── errors.py            RequestError e os handlers que devolvem JSON
│   ├── data/
│   │   ├── reader.py        leitura dos CSVs e conversão de tipos
│   │   └── repository.py    índices em memória, filtros e agregações
│   ├── realtime/            o canal
│   │   ├── __init__.py      registra /ws, checa Origin, monta os limites
│   │   ├── protocol.py      formato dos frames (puro)
│   │   ├── params.py        validação dos params de um comando (puro)
│   │   ├── actions.py       registry: nome → cálculo, e o streaming de progresso
│   │   ├── handlers.py      os cálculos em si (puros)
│   │   └── channel.py       laço da conexão: recebe, despacha, envia
│   └── api/
│       └── health.py        /api/health, o único endpoint HTTP
├── tools/
│   └── ws_client.py        cliente de terminal para falar com o canal
└── tests/                  leitor, repositório, canal, config e contrato
```

A fonte de dados é `backend/dataset/normalizado/` (gerada por
`backend/dataset/normalizar_dataset.py`). São menos de mil solicitações, então os quatro
CSVs são carregados uma vez na criação da aplicação e servidos a partir de dicionários por
id — sem banco e sem pandas. Trocar o diretório é só ajustar `DATASET_DIR`; se ele não
existir, a aplicação falha na subida com uma mensagem dizendo o que rodar.

O caminho do canal é configurável em `WS_PATH` (padrão `/ws`), e `/api/health` informa qual
é — o front pode descobrir em vez de ter o valor fixo no código.

## O canal

Abra `ws://host/ws`. O servidor manda um `welcome` e fica esperando comandos:

```json
{ "id": "c1", "action": "queue.list", "params": { "oncological": true, "size": 20 } }
```

O `id` é seu e é opaco para o servidor: ele volta em **todos** os frames daquele comando,
que é como você liga o progresso de um cálculo à chamada que o disparou. Vários comandos
podem estar em andamento na mesma conexão.

Toda resposta carrega um `type`:

| `type` | Quando | Campos |
|---|---|---|
| `welcome` | ao conectar | `protocol`, `reference_date`, `dataset`, `actions` |
| `progress` | durante um cálculo longo | `id`, `action`, `completed`, `total`, `percent`, `label` |
| `result` | fim de um comando | `id`, `action`, `payload` |
| `error` | comando falhou | `id`, `action`, `error: {message, status, details?}` |

Um comando inválido rende um `error` e **não fecha a conexão** — pode haver cálculo em
andamento nela. O `status` segue a convenção HTTP: 400 parâmetro inválido, 404 não existe,
500 bug nosso (a mensagem interna nunca é exposta).

### Ações

| Ação | `params` | `payload` |
|---|---|---|
| `queue.list` | filtros, `sort_by`, `order`, `page`, `size` | `{data, pagination, sort}` |
| `queue.request` | `request_id` | `{request, procedure, events, total_events}` |
| `queue.events` | `request_id`, `page`, `size` | `{data, pagination}` |
| `patient.events` | `patient_id`, `page`, `size` | `{data, pagination}` |
| `queue.prioritize` | os filtros de `queue.list` | `{strategy, provisional, total, data}` — emite `progress` |
| `catalog.procedures` | — | `{data, total}` |
| `catalog.swalis` | — | `{data, total}` |
| `catalog.filters` | — | `{specialties, priorities, sort_fields}` |
| `stats.summary` | — | agregados da fila |

O `welcome` lista as ações disponíveis, então não precisa duplicar esta tabela no front.

Filtros de `queue.list`: `specialty`, `priority` (`alta`/`media`/`baixa`), `city`,
`procedure_id`, `oncological` (booleano, derivado do CID), `min_days`, `max_days`,
`min_age`, `search` (id, nome, procedimento, CID, justificativa e observações — ignora
acento e caixa). Ordenação: `sort_by` (padrão `dias_em_fila`), `order` (`desc`/`asc`).

Os **nomes** dos parâmetros são em inglês; os **valores** são os termos do dataset, porque é
o que está nos dados: `priority: "alta"`, `sort_by: "dias_em_fila"`. Como o comando é JSON,
`oncological` aceita `true`/`false` de verdade — e também `"yes"`/`"no"`, `"sim"`/`"nao"`,
`"1"`/`"0"`, que é o que a query string aceitava. Acento e caixa são ignorados nos filtros
de texto: `"oftalmologia"` e `"Oftalmologia"` dão o mesmo resultado.

### Consumindo do front (React + TypeScript)

Os frames formam uma união discriminada, então o `switch` abaixo é verificado pelo
compilador: se um `type` novo aparecer no protocolo, o `never` do `default` acusa.

```ts
// channel.ts
export type CommandId = string | number | null;

export type Welcome = {
  type: "welcome";
  protocol: number;
  reference_date: string;
  dataset: Record<string, number>;
  actions: string[];
};
export type Progress = {
  type: "progress";
  id: CommandId; action: string;
  completed: number; total: number; percent: number; label: string | null;
};
export type Result<P = unknown> = {
  type: "result"; id: CommandId; action: string; payload: P;
};
export type ServerError = {
  type: "error"; id: CommandId; action: string | null;
  error: { message: string; status: number; details?: unknown };
};
export type ServerFrame = Welcome | Progress | Result | ServerError;
```

```ts
// useChannel.ts — reconecta com backoff; `call` devolve uma Promise do payload
import { useCallback, useEffect, useRef, useState } from "react";
import type { Progress, ServerFrame, Welcome } from "./channel";

type Pending = {
  resolve: (payload: unknown) => void;
  reject: (reason: Error) => void;
  onProgress?: (step: Progress) => void;
};

export function useChannel(url: string) {
  const socket = useRef<WebSocket | null>(null);
  const pending = useRef(new Map<string, Pending>());
  const [welcome, setWelcome] = useState<Welcome | null>(null);
  const [online, setOnline] = useState(false);

  useEffect(() => {
    let unmounted = false;
    let attempt = 0;
    let timer = 0;

    const connect = () => {
      const ws = new WebSocket(url);
      socket.current = ws;

      ws.onopen = () => { attempt = 0; setOnline(true); };

      ws.onmessage = (event) => {
        const frame: ServerFrame = JSON.parse(event.data);
        const key = String(frame.type === "welcome" ? "" : frame.id);
        switch (frame.type) {
          case "welcome":
            setWelcome(frame);
            return;
          case "progress":
            pending.current.get(key)?.onProgress?.(frame);
            return;
          case "result":
            pending.current.get(key)?.resolve(frame.payload);
            pending.current.delete(key);
            return;
          case "error":
            pending.current.get(key)?.reject(new Error(frame.error.message));
            pending.current.delete(key);
            return;
          default: {
            const exhaustive: never = frame;
            throw new Error(`frame desconhecido: ${JSON.stringify(exhaustive)}`);
          }
        }
      };

      ws.onclose = () => {
        setOnline(false);
        // Quem estava esperando não vai receber resposta nesta conexão.
        pending.current.forEach((p) => p.reject(new Error("conexão fechada")));
        pending.current.clear();
        if (!unmounted) {
          timer = window.setTimeout(connect, Math.min(1000 * 2 ** attempt++, 10_000));
        }
      };
    };

    connect();
    return () => { unmounted = true; window.clearTimeout(timer); socket.current?.close(); };
  }, [url]);

  const call = useCallback(
    <P,>(action: string, params: Record<string, unknown> = {},
         onProgress?: (step: Progress) => void) =>
      new Promise<P>((resolve, reject) => {
        const ws = socket.current;
        if (!ws || ws.readyState !== WebSocket.OPEN) {
          reject(new Error("conexão não está aberta"));
          return;
        }
        const id = crypto.randomUUID();
        pending.current.set(id, {
          resolve: resolve as (payload: unknown) => void, reject, onProgress,
        });
        ws.send(JSON.stringify({ id, action, params }));
      }),
    [],
  );

  return { online, welcome, call };
}
```

```tsx
const { call, online } = useChannel("ws://localhost:5000/ws");
const [percent, setPercent] = useState(0);

const priorizar = () =>
  call("queue.prioritize", { specialty: "ortopedia" }, (step) => setPercent(step.percent));
```

### Testar à mão, sem front

`tools/ws_client.py` conversa com o canal pelo terminal. Usa o `simple-websocket` que já
vem com o flask-sock, então não precisa instalar nada:

```bash
python wsgi.py                                   # num terminal
python tools/ws_client.py                        # noutro: modo interativo
python tools/ws_client.py stats.summary           # um comando e sai
python tools/ws_client.py queue.list size=3 oncological=true
python tools/ws_client.py queue.prioritize        # mostra o progresso chegando
python tools/ws_client.py stats.summary --raw | jq .payload.wait_days
```

Os pares `chave=valor` viram JSON de verdade: `size=3` é número, `oncological=true` é
booleano, `asa=null` é nulo, o resto é texto. No modo interativo o `welcome` lista as ações
e cada linha é um comando:

```
> catalog.swalis
ok catalog.swalis · 5 registros
> queue.request request_id=sol-2025-00048
ok queue.request · request, procedure, events, total_events
> queue.list page=0
erro 400 em queue.list: parameter 'page' must be >= 1
```

Com `--raw` cada frame sai como uma linha de JSON, para passar no `jq`. O processo sai com
1 se o comando terminou em `error`, o que serve em script. O health check continua sendo
só um `curl`:

```bash
curl localhost:5000/api/health
```

## Decisões que afetam quem consome o canal

- **Um cálculo longo reporta progresso.** Uma ação pode ser um gerador que emite
  `Progress(completed, total, label)`; o canal traduz isso em frames `progress` com o `id`
  do comando. Quem escreve o cálculo não toca em socket nenhum — por isso ele é testável
  sem transporte.
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
- **Tudo que é nosso está em inglês; o que é do dataset, não.** Código, ações, parâmetros
  e chaves de envelope (`data`, `pagination`, `payload`, `error`) em inglês. Nomes de coluna
  (`solicitacao_id`, `dias_em_fila`, `oncologico_cid`) e valores de domínio (`alta`,
  `media`, `baixa`) ficam como estão: são o dado, documentado em
  `backend/dataset/dicionario_dados.md`. Então `sort_by: "dias_em_fila"` é o esperado, não
  um descuido.
- **O `.env` é lido pelos dois modos de subir.** `wsgi.py` chama `load_dotenv` antes de
  importar `app`, porque `Config` lê `os.environ` no corpo da classe — carregar depois não
  teria efeito. Variável já exportada no shell vence o arquivo.
- **O handshake não passa por CORS.** O navegador abre WebSocket de qualquer página, então
  a checagem de `Origin` é nossa: com `CORS_ORIGINS=*` (padrão de desenvolvimento) tudo
  entra; com uma lista, só ela. Restrinja antes de qualquer exposição pública.

## Ainda não implementado

O **algoritmo de priorização** e o `fila_priorizada.csv` não estão aqui.

A ação `queue.prioritize` já existe, mas é o **encaixe do transporte, não a regra**: ela
ordena por tempo de espera e nada mais, declara isso em `strategy` e `provisional: true`,
ignora a regra de ouro e não passaria pelo
`backend/dataset/verificar_fila_priorizada.py`. Ela serve para o front integrar contra um
contrato estável desde já.

Quando a regra real entrar, o lugar é `app/prioritization/` em função pura (recebe fila +
eventos, devolve posição + justificativa) chamada de dentro de `handlers.prioritize`. O
contrato do cliente não muda: mesma ação, mesmos frames, mesmas chaves
`solicitacao_id`/`posicao`/`justificativa` que o entregável pede.
