# NexCore · frontend

React + TypeScript + Vite. Painel do administrador da regulação: início, fila priorizada pelo Neco e auditoria.

```bash
npm install
npm run dev      # http://localhost:5173
npm run build
```

Por padrão roda com o backend simulado (`src/mock`), sem servidor.

Com o backend real (Flask em `backend/`, porta 5000):

```bash
cd backend && python wsgi.py          # outro terminal
cd frontend && npm run dev:backend    # usa .env.backend
```

Se `/painel/impacto` ou `/fila/exportar` responderem 404 (backend antigo), o front usa o relatório de referência `src/mock/impacto.json` e monta o `fila_priorizada.csv` a partir da fila ao vivo. No modo backend não há "Simular evento": as atualizações em tempo real vêm das ações dos administradores e, quando existir, da ingestão (`/fila/eventos`).

## Estrutura

```
src/
  api/        contrato (types.ts), interface Backend e cliente HTTP + WebSocket
  mock/       backend em memória com amostra do dataset e eventos roteirizados
  domain/     regras puras: classes, prazos, regra de ouro, relocação
  state/      QueueContext: estado da fila, auditoria e atividade
  components/ Neco, layout, painel do paciente, modal de reordenação
  pages/      Home, Queue, Audit
```

## Contrato com o backend

Base: `VITE_API_URL` + `/hospitais/{hospital}`.

| Método | Rota | Uso |
|---|---|---|
| GET | `/fila` | `QueueSnapshot` (carga inicial) |
| GET | `/auditoria` | `AuditEntry[]` |
| POST | `/fila/{id}/reordenar` | body `ReorderRequest`, retorna `AuditEntry`; 4xx com `{detail}` se violar a regra de ouro |
| POST | `/fila/{id}/validar` | retorna `AuditEntry` |
| GET | `/pendencias` | `Pendency[]`: inconsistências de dados para resolver |
| POST | `/pendencias/{id}/resolver` | body `ResolveRequest` (`action`, `note?`), retorna `AuditEntry` do tipo `data` |
| GET | `/painel/equidade` | `EquityReport`: municípios (com lat/lon) e grupos por distância, idade e sexo |
| GET | `/painel/resumo` | `QueueSummary` para o telão; o topo da fila vem só com iniciais |
| GET | `/painel/impacto` | `ImpactReport`: verificador oficial na fila do Neco e na manual, matriz e quem mais subiu |
| GET | `/fila/exportar` | `text/csv` com o `fila_priorizada.csv` oficial |
| POST | `/neco/perguntar` | body `{question}`, retorna `NecoAnswer` (`text`, `entryIds?`, `suggestions?`) |

WebSocket em `VITE_WS_URL?hospital={hospital}`. O servidor só envia; ações do usuário vão por REST. Mensagens (JSON, campo `type`):

- `queue.snapshot`: enviado ao conectar e reconectar. Fila completa.
- `queue.patch`: só as entradas que mudaram (`entries`), `total` e `removed` opcional.
- `audit.appended`: novo registro de auditoria.
- `pendency.resolved`: pendência resolvida (por qualquer administrador).
- `activity`: frase curta para o feed da home.

Textos do Neco por IA: o painel do paciente pede `GET /fila/{id}/explicacao` e mostra o texto local até a resposta chegar; só troca quando vem `source: "ia"` (com o selo "IA · conferido"). Equidade e impacto pedem o comentário em `/painel/equidade/comentario` e `/painel/impacto/comentario`. Em todos os casos o Neco pensa enquanto a API responde e depois escreve o texto (da IA ou, se falhar, o por regras) com a mesma animação.

Cada `QueueEntry` traz `highlights`: trechos do texto livre (`clinicalNote`/`regulationNote`, com `start`/`end`) que o Neco usou, classificados como `urgency`, `events`, `symptoms` ou `red_flag`.

O "Pergunte ao Neco" deve ser um LLM com ferramentas de consulta à fila no backend (a chave nunca vai para o front). Ele explica e consulta; não altera posições.

## Telas

- `/` início · `/fila` e `/fila/:id` · `/pendencias` · `/equidade` · `/impacto` · `/auditoria`
- `/telao`: painel para TV, sem nomes completos. Abra em outra janela e use tela cheia. No modo mock, as ações feitas na aba principal são repetidas no telão (BroadcastChannel).
- Ctrl+K abre o "Pergunte ao Neco" em qualquer tela.

Os agregados do mock (`src/mock/stats.json`) foram gerados a partir do dataset completo (941 solicitações). `impacto.json` é a mesma referência que `backend/tests/dados/impacto_referencia.json`; se o painel de impacto mudar, atualize os dois.

Tipos completos em [src/api/types.ts](src/api/types.ts).
