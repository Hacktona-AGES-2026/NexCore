# NexCore · frontend

React + TypeScript + Vite. Painel do administrador da regulação: início, fila priorizada pelo Neco e auditoria.

```bash
npm install
npm run dev      # http://localhost:5173
npm run build
```

Por padrão roda com o backend simulado (`src/mock`), sem servidor. Para apontar para o backend real, copie `.env.example` para `.env` e use `VITE_USE_MOCK=false`.

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

WebSocket em `VITE_WS_URL?hospital={hospital}`. O servidor só envia; ações do usuário vão por REST. Mensagens (JSON, campo `type`):

- `queue.snapshot`: enviado ao conectar e reconectar. Fila completa.
- `queue.patch`: só as entradas que mudaram (`entries`), `total` e `removed` opcional.
- `audit.appended`: novo registro de auditoria.
- `activity`: frase curta para o feed da home.

Tipos completos em [src/api/types.ts](src/api/types.ts).
