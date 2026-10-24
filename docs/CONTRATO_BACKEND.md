# O que o backend precisa implementar

Documento para o time de backend. O frontend (`frontend/`) já está pronto e roda hoje contra um **backend simulado** (`frontend/src/mock/`). Tudo o que está aqui é o que esse simulado faz e o servidor real precisa fazer.

- **Contrato de tipos (fonte da verdade):** [`frontend/src/api/types.ts`](../frontend/src/api/types.ts)
- **Implementação de referência executável:** [`frontend/src/mock/mockBackend.ts`](../frontend/src/mock/mockBackend.ts), [`neco.ts`](../frontend/src/mock/neco.ts), [`highlights.ts`](../frontend/src/mock/highlights.ts)
- **Saída de referência dos agregados (dataset completo):** [`frontend/src/mock/stats.json`](../frontend/src/mock/stats.json)

Para o front usar o servidor real: `frontend/.env` com `VITE_USE_MOCK=false`, `VITE_API_URL`, `VITE_WS_URL` e `VITE_HOSPITAL_ID`.

---

## Status da integração (24/10)

O front roda contra o backend real com `npm run dev:backend`. Testado ponta a ponta: fila completa (941), reordenação com regra de ouro (422), validação, auditoria encadeada, pendências, resumo, equidade, impacto (verificador oficial no servidor, ~3 s), exportação do CSV oficial, Pergunte ao Neco e WebSocket (`queue.snapshot`, `queue.patch`, `audit.appended`, `pendency.resolved`, `activity`). Todos os formatos batem com `types.ts`.

Ainda faltam no backend:

| Rota | Hoje o front faz |
|---|---|
| `POST /fila/entradas`, `POST /fila/eventos` | nada: sem ingestão, a fila só muda por ação humana. É o que faz a demonstração "ao vivo" funcionar |

---

## 1. Arquitetura da comunicação

| Canal | Para quê |
|---|---|
| **REST** | Carga inicial e todas as ações do administrador (reordenar, validar, resolver pendência, perguntar). Cada ação devolve sucesso ou erro claro. |
| **WebSocket** | Só servidor → front. Empurra mudanças da fila, auditoria e atividade em tempo real para todos os administradores conectados. |
| **REST de ingestão** | Sistemas externos mandam novas entradas e eventos clínicos. O Neco recalcula e o resultado sai pelo WebSocket. |

Regras gerais:

- Base: `{VITE_API_URL}/hospitais/{hospitalId}` (ex.: `http://localhost:5000/v1/hospitais/hsl`). Todo dado é escopado por hospital.
- JSON em **camelCase**, datas `AAAA-MM-DD`, instantes em ISO 8601.
- Erro: status 4xx/5xx com corpo `{"detail": "mensagem em português para mostrar ao usuário"}`. O front exibe o `detail` como está.
- Autor das ações: por enquanto o front não tem login. Usar um usuário fixo ("Marina Albuquerque") ou ler de um header `Authorization` se der tempo. O nome do autor vai na auditoria.

### Diferenças em relação ao backend atual (Flask em `backend/`)

1. **Prefixo e porta:** hoje as rotas são `/api/...` na porta 5000. Ou criem o prefixo `/v1/hospitais/<hospital>`, ou combinem outro e eu ajusto `http.ts`.
2. **Nomes de campos:** o dataset está em português snake_case (`solicitacao_id`); o front espera o formato da seção 3 (`id`, `daysWaiting`, ...). Fazer o mapeamento na camada da API.
3. **Paginação:** o front quer a fila **inteira** de uma vez (941 itens é pouco).
4. **WebSocket no Flask:** o cliente usa WebSocket **puro** (não Socket.IO). Sugestão: `flask-sock`. Rodar com **um único processo** para o broadcast em memória funcionar (ex.: `gunicorn -w 1 -k gthread --threads 50 wsgi:app`).
5. **Estado mutável:** hoje o repositório é só leitura. Reordenação, travas, auditoria e pendências resolvidas precisam de estado (memória serve para a hackathon; SQLite se quiserem sobreviver a reinício).

---

## 2. Endpoints REST

| Método | Rota | Corpo | Resposta |
|---|---|---|---|
| GET | `/fila` | — | `QueueSnapshot` |
| GET | `/auditoria` | — | `AuditEntry[]` (mais recente primeiro) |
| POST | `/fila/{id}/reordenar` | `ReorderRequest` | `AuditEntry` |
| POST | `/fila/{id}/validar` | — | `AuditEntry` |
| GET | `/pendencias` | — | `Pendency[]` |
| POST | `/pendencias/{id}/resolver` | `ResolveRequest` | `AuditEntry` |
| GET | `/painel/equidade` | — | `EquityReport` |
| GET | `/painel/resumo` | — | `QueueSummary` |
| GET | `/painel/impacto` | — | `ImpactReport` |
| GET | `/fila/exportar` | — | `text/csv`: o `fila_priorizada.csv` oficial |
| POST | `/neco/perguntar` | `AskRequest` | `NecoAnswer` |
| POST | `/fila/entradas` | nova solicitação | `QueueEntry` criada *(ingestão; o front não chama)* |
| POST | `/fila/eventos` | evento clínico | `202` *(ingestão; o front não chama)* |

### `POST /fila/{id}/reordenar`

```json
{ "position": 210, "reason": "Critério clínico não considerado", "justification": "Angina instável confirmada com a cardiologia..." }
```

Validações (o front já checa, **o servidor deve checar de novo**):

- `justification` com pelo menos 40 caracteres; `reason` obrigatório; `1 ≤ position ≤ total`.
- **Regra de ouro:** se a nova ordem deixar algum paciente com CID iniciado por `C` abaixo de algum paciente classe `D`, responder `422` com `detail` explicando quem ficaria abaixo de quem.

Efeitos: move o paciente, desloca os demais, marca `locked: true` (recálculos automáticos não mexem mais nele), grava `AuditEntry` `kind: "manual"` com `justification = "{reason}. {justification}"`, e envia pelo WebSocket `queue.patch` (todos os que mudaram de posição), `audit.appended` e `activity`.

### `POST /fila/{id}/validar`

Grava `AuditEntry` `kind: "validation"` (from = to = posição atual) e envia `audit.appended`.

---

## 3. Formato de `QueueEntry`

Exemplo com valores ilustrativos (campos opcionais podem ser omitidos):

```json
{
  "id": "SOL-2025-00274",
  "patientId": "PAC-00442",
  "name": "Gabriela Ramos Quadros",
  "sex": "F",
  "age": 67,
  "city": "Porto Alegre",
  "procedure": "Revascularizacao do miocardio",
  "specialty": "Cirurgia Cardiaca",
  "cid": "I20.0",
  "cidDescription": "Angina instavel",
  "asa": "3",
  "comorbidities": "HAS; DM2",
  "pain": "6",
  "limitation": "moderada",
  "clinicalNote": "Angina instavel, internacao recente, lesao de tronco de coronaria esquerda. Cirurgia com prioridade.",
  "regulationNote": "Pct relata que foi ao PS 2x no ultimo mes por dor.",
  "enteredAt": "2025-09-09",
  "daysWaiting": 409,
  "manualPriority": "alta",
  "oncologic": false,

  "position": 404,
  "urgencyClass": "C",
  "score": 48.8,
  "factors": [
    { "key": "urgency",  "value": 12,  "max": 40 },
    { "key": "wait",     "value": 25,  "max": 25 },
    { "key": "events",   "value": 6,   "max": 20 },
    { "key": "symptoms", "value": 5.8, "max": 12 }
  ],
  "classReason": "dor moderada (6/10)",
  "warnings": [
    { "level": "info", "text": "O texto cita \"lesao de tronco de coronaria esquerda\", sinal de gravidade que não está nos campos estruturados." }
  ],
  "locked": false,
  "pendingConfirmation": false,
  "events": [
    { "date": "2026-08-06", "type": "internacao", "result": "alta", "value": "4", "description": "...", "origin": "Hospital Sao Lucas" }
  ],
  "highlights": [
    { "field": "clinicalNote", "start": 0, "end": 15, "kind": "urgency" },
    { "field": "clinicalNote", "start": 34, "end": 72, "kind": "red_flag" }
  ]
}
```

### Mapeamento a partir do dataset normalizado

| Front | Dataset | Observação |
|---|---|---|
| `id`, `patientId` | `solicitacao_id`, `paciente_id` | |
| `name`, `sex`, `age` | `nome_paciente`, `sexo`, `idade` | |
| `city` | `municipio_norm` | |
| `procedure`, `specialty` | `procedimento`, `especialidade` | |
| `cid`, `cidDescription` | `cid_principal`, `cid_descricao` | |
| `asa`, `comorbidities`, `pain`, `limitation` | `asa`, `comorbidades`, `intensidade_dor_eva`, `limitacao_funcional_norm` | omitir quando vazio |
| `clinicalNote`, `regulationNote` | `justificativa_clinica`, `observacoes` | |
| `enteredAt`, `daysWaiting` | `data_entrada_fila`, `dias_em_fila` | |
| `manualPriority` | `prioridade_regulacao_norm` | |
| `oncologic` | `oncologico_cid` | **sempre pelo CID, nunca pela flag** |
| `events[]` | `eventos_clinicos_normalizados.csv` | ignorar `duplicata_conteudo = sim`; tipos/resultados em `tipo_evento_norm`/`resultado_norm` |
| demais campos | calculados pelo Neco (seção 4) | |

---

## 4. Lógica do Neco (o coração do backend)

### 4.1 Classe de urgência (SWALIS adaptado)

| Classe | Prazo | Regra atual do protótipo |
|---|---|---|
| A1 | 15 d | CID `C*` **e** (imagem com progressão **ou** PS/internação nos últimos 180 d) |
| A2 | 21 d | CID `C*` **ou** biópsia positiva |
| B | 60 d | CID D37–D48/R91, dor ≥ 7, limitação grave, ou ≥ 2 PS/internações em 180 d |
| C | 180 d | dor ≥ 4, limitação moderada, ou 1 PS/internação em 180 d |
| D | 360 d | o resto |

`classReason` é a frase curta que justifica a classe (ex.: `"câncer confirmado pelo CID C54.1 com piora recente"`, `"dor moderada (6/10)"`). Exemplos em `classReason()` no mock.

### 4.2 Índice (0 a 97)

| Fator | Máx. | Cálculo do protótipo |
|---|---|---|
| `urgency` | 40 | A1 40 · A2 34 · B 22 · C 12 · D 4 |
| `wait` | 25 | `25 × min(dias / prazo da classe, 2) / 2` |
| `events` | 20 | `6 × PS/internações(180 d) + 4 × relatos de piora + 8 se progressão + 6 se biópsia positiva com CID não-C`, teto 20 |
| `symptoms` | 12 | `0,8 × dor + {grave: 4, moderada: 2,5, leve: 1}` |

Os pesos são do protótipo; o time de priorização pode ajustar, mas mantenha o formato `factors` para o front.

### 4.3 Ordenação e travas

1. Ordenar por classe (A1 > A2 > B > C > D) e, dentro da classe, por `score` decrescente.
2. Entradas com `locked: true` mantêm a posição definida manualmente; as demais se encaixam em volta.
3. **Regra de ouro** sempre: nenhum `C*` abaixo de classe D. Validar depois de cada recálculo e de cada reordenação.
4. `position` é 1..N contínua.

### 4.4 Avisos (`warnings`) e lista de revisão

O front mostra na home ("Precisam da sua revisão") todo paciente com `warnings` não vazio que ainda não foi validado nem movido. Gerar aviso quando:

- `red_flag` no texto livre e classe B, C ou D;
- CID `I20*` (angina) sem evento que confirme;
- flag oncológica do cadastro diverge do CID;
- call center informou cirurgia em outro serviço ou desistência (`level: "critical"`, e `pendingConfirmation: true`).

**O Neco nunca remove paciente da fila sozinho.**

### 4.5 Destaques no texto (`highlights`)

Trechos de `clinicalNote`/`regulationNote` que pesaram, com índices `start`/`end` (caracteres) e `kind`:

- `red_flag`: sinais de gravidade (lesão de tronco, síncope, melena, queda de Hb, suboclusão, emagrecimento, perda ponderal, dessaturação, acamado...)
- `urgency`: diagnóstico (carcinoma, neoplasia, BI-RADS, AP confirmado, angina...)
- `events`: internação, PS, piora
- `symptoms`: dor, limitação, não consegue..., muletas

O mock usa regex (`highlights.ts`); dá para começar igual e evoluir para NLP/LLM. Trechos não podem se sobrepor.

### 4.6 Ingestão e recálculo

`POST /fila/entradas` e `POST /fila/eventos` (formato livre, sugerido igual às linhas dos CSVs). A cada chegada:

1. atualizar a solicitação (eventos, classe, fatores, avisos, destaques);
2. reordenar respeitando travas e regra de ouro;
3. gravar `AuditEntry` (`kind: "intake"` para entrada nova, `"recalc"` para evento) com justificativa em português dizendo o que mudou e por quê;
4. enviar `queue.patch` só com quem mudou, `audit.appended` e `activity`.

Evento de HbA1c é critério de preparo, **não** muda prioridade (pode gerar auditoria dizendo isso).

---

## 5. Auditoria

```json
{
  "id": "AUD-00042", "at": "2026-10-24T06:11:00Z", "author": "Marina Albuquerque",
  "kind": "manual", "entryId": "SOL-2025-00274", "entryName": "Gabriela Ramos Quadros",
  "from": 406, "to": 210, "justification": "Critério clínico não considerado. ...",
  "hash": "b8168eef...", "prevHash": "7ef0a381..."
}
```

- `kind`: `recalc` (Neco por evento) · `intake` (entrada nova) · `manual` (reordenação) · `validation` (concordou) · `data` (pendência resolvida).
- `from: null` para entrada nova. Em `data`, `to` pode ser 0.
- **Só inclusão, nunca edição ou exclusão.**
- `hash = SHA-256(prevHash + JSON canônico de [at, author, kind, entryId, from, to, justification])`; o primeiro usa `prevHash = "00000000"`. O front confere que cada `prevHash` bate com o `hash` do registro anterior e mostra "Cadeia íntegra".

---

## 6. WebSocket

URL: `{VITE_WS_URL}?hospital={hospitalId}`. Mensagens JSON com campo `type`:

| `type` | Quando | Corpo |
|---|---|---|
| `queue.snapshot` | **logo ao conectar** (e a cada reconexão) | `{ snapshot: QueueSnapshot }` |
| `queue.patch` | qualquer mudança na fila | `{ total, entries: QueueEntry[] (só as alteradas), removed?: string[] }` |
| `audit.appended` | todo novo registro de auditoria | `{ entry: AuditEntry }` |
| `pendency.resolved` | pendência resolvida | `{ id }` |
| `activity` | frase curta para o feed da home e do telão | `{ at, text }` (ex.: `"Diego subiu de 407 para 221 após ida ao PS"`) |

O front reconecta sozinho com espera crescente e se ressincroniza pelo `queue.snapshot`.

---

## 7. Pendências de dados — implementado

Toda pendência tem **o mesmo formato**, qualquer que seja o tipo, e um único painel de correção no front desenha todas, inclusive tipos novos. Um detector novo só precisa produzir este formato (`backend/app/regulation/pendencies.py`):

```json
{ "id": "PEN-0067", "kind": "biopsy", "kindLabel": "Biópsia × CID", "title": "...", "detail": "...", "name": "...",
  "entryIds": ["SOL-..."], "risk": "alto", "riskReason": "...",
  "divergences": [{ "field": "cid", "label": "Diagnóstico",
                    "values": [{ "source": "CID principal", "value": "D44.0 · ..." }, { "source": "Biópsia de 19/09/2026", "value": "positiva · ..." }] }],
  "evidence": [{ "label": "Biópsia positiva", "date": "2026-09-19", "text": "..." }],
  "actions": [{ "id": "update_cid", "label": "Corrigir o CID", "description": "...", "requiresJustification": true,
                "danger": false, "changesQueue": true,
                "fields": [{ "name": "cid", "label": "CID correto", "type": "text", "required": true, "suggested": "C73", "pattern": "..." }] }],
  "suggestion": { "actionId": "update_cid", "reason": "..." } }
```

- `POST /pendencias/{id}/resolver` com `{ action, values, note }`: valida os campos da ação, **muda o dado de verdade** numa cópia da fila (nunca no dataset), recalcula, confere a regra de ouro, audita o antes e o depois e envia `pendency.resolved` + `queue.patch`. Pendências que ficam sem solicitação ativa são encerradas junto.
- `POST /pendencias/{id}/simular` com `{ action, values }`: roda o mesmo código num rascunho e devolve `{ summary, changes: [{entryId, name, from, to, classFrom, classTo}] }` sem mudar nada.
- Risco: `alto` quando a pendência pode esconder um paciente grave (CID benigno com marcação de câncer, biópsia positiva, evento órfão importante com outra solicitação ativa); `medio` para duplicatas e saída da fila; `baixo` para o resto.
- Ações de hoje: `fix_cadastro`, `update_cid`, `keep`, `unrelated` (biópsia não é deste pedido), `merge` (com `keep`, padrão a entrada mais antiga), `keep_both`, `remove` (com `confirmacao`), `link` (com `target`), `archive`.

---

## 8. Painéis

### `GET /painel/equidade` → `EquityReport`

- `cities[]`: por município — `name`, `lat`, `lon`, `total`, `avgWait` (média de `dias_em_fila`), `overdue` (dias > prazo da classe), `urgent` (A1+A2), `distanceKm` (média de `distancia_hospital_km`). **As coordenadas dos 38 municípios já estão em `stats.json`**; copiem de lá.
- `byDistance` (Até 50 km · 50 a 200 km · Mais de 200 km), `byAge` (18 a 39 · 40 a 59 · 60 a 74 · 75 ou mais), `bySex` (Mulheres · Homens): cada um com `label`, `total`, `avgWait`, `overduePct`.

Achado atual dos dados (bom para o pitch): quem mora a mais de 200 km espera em média 492 dias, contra 366 de quem mora até 50 km.

### `GET /painel/resumo` → `QueueSummary` (telão)

`total`, `oncologic`, `overdueTotal`, `byClass[]` (`cls`, `total`, `overdue`), `bySpecialty[]`, `waitBuckets[]` (0–90, 91–180, 181–365, 1–2 anos, 2+ anos) e `top[]` com as 12 primeiras posições **só com iniciais** (`"E.L.P."`), porque o telão é tela pública (LGPD).

---

### `GET /painel/impacto` → `ImpactReport` e `GET /fila/exportar`

Já existe uma implementação de referência em Python: [`entrega/gerar_entrega.py`](../entrega/gerar_entrega.py) com o cálculo em [`entrega/neco.py`](../entrega/neco.py) (só biblioteca padrão). Ela gera exatamente o `impacto.json` e o `fila_priorizada.csv` que o front consome.

- `/fila/exportar`: CSV com `solicitacao_id,posicao,justificativa` da fila **atual** (respeitando reordenações manuais).
- `/painel/impacto`: roda o verificador oficial (`verificar_fila_priorizada.py`) na fila do Neco e na fila manual de referência (prioridade manual, desempate por espera) e devolve os indicadores, a matriz classe × prioridade manual, os números de destaque e quem mais subiu. Pode ser calculado na subida e recalculado a cada mudança.

**Implementado** em `backend/app/regulation/impact.py` (cálculo puro) e `verifier.py` (roda o verificador por subprocess, sem importar). O relatório sai com `source: "backend"`, fica em cache até a ordem da fila mudar e, se o verificador não puder rodar (ex.: servidor sem pandas), a rota responde `503` com `detail`. O verificador lê os CSVs **de origem**: `VERIFIER_DATASET_DIR`, padrão `backend/dataset/`.

## 9. Pergunte ao Neco

`POST /neco/perguntar` com `{ "question": "Por que a Gabriela está na posição dela?" }` → 

```json
{ "text": "Gabriela Ramos Quadros está na posição 404 como Moderado (C)...", "entryIds": ["SOL-2025-00274"], "suggestions": [] }
```

- Implementar com **LLM com uso de ferramentas** (ex.: Claude pela API da Anthropic) no servidor. **A chave de API fica só no backend.**
- Ferramentas sugeridas para o modelo: buscar paciente por nome/ID, obter `QueueEntry`, listar fila com filtros (classe, especialidade, prazo vencido), `QueueSummary`, `EquityReport`, `Pendency[]`.
- Regras no prompt de sistema: responder em português, curto; **só usar dados das ferramentas, nunca inventar**; **não alterar posições** (ele explica, quem decide é o humano); devolver em `entryIds` os pacientes citados.
- Perguntas que o front sugere e devem funcionar: explicar posição de um paciente, comparar dois pacientes, contar casos por classe, listar quem passou do prazo por especialidade, falar de equidade e de pendências. O mock (`neco.ts`) responde essas mesmas perguntas por palavra-chave: serve de gabarito.

---

## 9.1 Textos do Neco por IA (Gemini) — implementado em `backend/app/neco_ia/`

Todo texto em que o Neco "fala" pode ser escrito pelo modelo, sempre com a mesma regra: **a posição, a classe e o índice vêm do cálculo; a IA só escreve sobre eles**.

| Onde | Rota | Formato |
|---|---|---|
| Por que o paciente está ali | `GET /fila/{id}/explicacao` | `NecoText` = `{text, points, source, verified}` |
| Comentário da equidade | `GET /painel/equidade/comentario` | `NecoText` |
| Comentário do impacto | `GET /painel/impacto/comentario` | `NecoText` |
| Pergunte ao Neco | `POST /neco/perguntar` | aceita `history: [{from: "me" \| "neco", text}]` |

- Os comentários dos painéis ficam em rotas próprias para o painel abrir na hora; o front mostra o Neco "pensando" até o comentário chegar e depois o escreve letra a letra. Se a rota falhar, o front escreve o texto por regras do mesmo jeito.
- **Entrada da IA**: só dados estruturados — fatores, eventos recentes, trechos destacados do texto, avisos, vizinhos, a auditoria do paciente (movimentações manuais com justificativa, validações) e `suggestedPosition` (onde o Neco colocaria sem travas; campo novo em `QueueEntry`).
- **Verificação**: todo número do texto precisa existir nos dados enviados; senão o texto é descartado. `source: "ia"` só quando o modelo respondeu e passou na verificação.
- **Reserva**: sem chave, cota estourada, timeout ou resposta fora do formato → texto por regras (`source: "regras"`), sem erro para o usuário. No chat, cai nas respostas por palavra-chave (`regulation/ask.py`).
- **Cache** por paciente + versão dos dados: um paciente custa uma chamada até mudar (evento, reordenação, validação). Equidade e impacto custam uma chamada por mudança nos números.
- **Chat com ferramentas só de leitura** (`neco_ia/chat.py`): buscar pacientes, detalhar solicitação, listar fila com filtros, resumo, equidade, pendências, histórico de auditoria e regras do Neco. Nenhuma ferramenta altera a fila.
- **Plano gratuito**: `NECO_IA_RPM` espaça as chamadas; se a espera passar de 3 s, usa a reserva em vez de travar a tela.
- **Configuração** (`backend/.env`): `GEMINI_API_KEY`, `GEMINI_MODEL` (padrão `gemini-3.1-flash-lite`; confiram no Google AI Studio o modelo e os limites atuais), `NECO_IA_ENABLED`, `NECO_IA_RPM`. A chave nunca vai para o front nem para o Git.

---

## 10. Ordem sugerida

| Prioridade | O quê | Por quê |
|---|---|---|
| **P0** | `GET /fila` com cálculo do Neco (seções 3 e 4.1–4.4), WebSocket com `queue.snapshot`, `reordenar`, `validar`, `GET /auditoria` com hash | É o fluxo principal da demonstração |
| **P1** | Ingestão (`/fila/entradas`, `/fila/eventos`) com recálculo e `queue.patch` / `audit.appended` / `activity` | Mostra a fila "viva" |
| **P2** | `/pendencias` + resolver, `/painel/resumo`, `/painel/equidade`, `/painel/impacto`, `/fila/exportar` | Pendências, telão, equidade e impacto (este já tem script de referência) |
| **P3** | `/neco/perguntar` com LLM, `highlights` mais espertos que regex | Diferencial; o front já funciona com o mock enquanto isso |

Hoje a troca é tudo ou nada (`VITE_USE_MOCK`): ou o front usa o mock inteiro, ou o servidor inteiro. Se quiserem integrar por partes, me avisem que eu faço o front cair no mock só nas rotas que ainda não existirem.
