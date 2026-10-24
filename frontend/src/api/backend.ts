import type { AuditEntry, ConnectionStatus, QueueSnapshot, ReorderRequest, ServerMessage } from "./types";

export interface Backend {
  getQueue(): Promise<QueueSnapshot>;
  getAudit(): Promise<AuditEntry[]>;
  reorder(entryId: string, req: ReorderRequest): Promise<AuditEntry>;
  validate(entryId: string): Promise<AuditEntry>;
  /** Abre o canal em tempo real. Retorna a função que fecha. */
  subscribe(onMessage: (m: ServerMessage) => void, onStatus: (s: ConnectionStatus) => void): () => void;
  /** Só existe no mock: injeta o próximo evento roteirizado. */
  simulateEvent?: () => void;
}

const env = import.meta.env;
export const config = {
  useMock: env.VITE_USE_MOCK !== "false",
  apiUrl: env.VITE_API_URL ?? "http://localhost:8000/v1",
  wsUrl: env.VITE_WS_URL ?? "ws://localhost:8000/v1/ws",
  hospitalId: env.VITE_HOSPITAL_ID ?? "hsl",
};
