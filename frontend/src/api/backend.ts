import type {
  AskRequest, AuditEntry, ConnectionStatus, EquityReport, ImpactReport, NecoAnswer, Pendency, QueueSnapshot, QueueSummary, ReorderRequest,
  ResolveRequest, ServerMessage,
} from "./types";

export interface Backend {
  getQueue(): Promise<QueueSnapshot>;
  getAudit(): Promise<AuditEntry[]>;
  getPendencies(): Promise<Pendency[]>;
  getEquity(): Promise<EquityReport>;
  getSummary(): Promise<QueueSummary>;
  getImpact(): Promise<ImpactReport>;
  /** fila_priorizada.csv oficial (solicitacao_id, posicao, justificativa). */
  exportQueueCsv(): Promise<string>;
  reorder(entryId: string, req: ReorderRequest): Promise<AuditEntry>;
  validate(entryId: string): Promise<AuditEntry>;
  resolvePendency(id: string, req: ResolveRequest): Promise<AuditEntry>;
  ask(req: AskRequest): Promise<NecoAnswer>;
  /** Abre o canal em tempo real. Retorna a função que fecha. */
  subscribe(onMessage: (m: ServerMessage) => void, onStatus: (s: ConnectionStatus) => void): () => void;
  /** Só existe no mock: injeta o próximo evento roteirizado. */
  simulateEvent?: () => void;
}

/** Erro HTTP do backend; `message` é o `detail` em português. */
export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

const env = import.meta.env;
export const config = {
  useMock: env.VITE_USE_MOCK !== "false",
  apiUrl: env.VITE_API_URL ?? "http://localhost:8000/v1",
  wsUrl: env.VITE_WS_URL ?? "ws://localhost:8000/v1/ws",
  hospitalId: env.VITE_HOSPITAL_ID ?? "hsl",
};
