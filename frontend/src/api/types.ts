// Contrato entre o front e o backend do Neco.
// REST: carga inicial e ações do administrador.
// WebSocket: o servidor empurra mudanças da fila em tempo real.

export type UrgencyClass = "A1" | "A2" | "B" | "C" | "D";

export interface ClinicalEvent {
  date: string; // AAAA-MM-DD
  type: string; // biopsia, pronto_socorro, internacao, ...
  result: string;
  value?: string;
  description: string;
  origin: string;
}

export interface ScoreFactor {
  key: "urgency" | "wait" | "events" | "symptoms";
  value: number;
  max: number;
}

export interface Warning {
  level: "info" | "critical";
  text: string;
}

export interface QueueEntry {
  id: string; // solicitacao_id
  patientId: string;
  name: string;
  sex: string;
  age: number;
  city: string;
  procedure: string;
  specialty: string;
  cid: string;
  cidDescription: string;
  asa?: string;
  comorbidities?: string;
  pain?: string;
  limitation?: string;
  clinicalNote: string;
  regulationNote?: string;
  enteredAt: string;
  daysWaiting: number;
  manualPriority?: string;
  oncologic: boolean;

  position: number;
  previousPosition?: number;
  urgencyClass: UrgencyClass;
  score: number;
  factors: ScoreFactor[];
  /** Frase do Neco explicando a classe, ex.: "dor moderada (6/10)". */
  classReason: string;
  warnings: Warning[];
  /** Posição travada manualmente pela regulação. */
  locked: boolean;
  pendingConfirmation: boolean;
  events: ClinicalEvent[];
}

export type AuditKind = "recalc" | "intake" | "manual" | "validation";

export interface AuditEntry {
  id: string;
  at: string; // ISO
  author: string;
  kind: AuditKind;
  entryId: string;
  entryName: string;
  from: number | null;
  to: number;
  justification: string;
  hash: string;
  prevHash: string;
}

export interface QueueSnapshot {
  hospitalId: string;
  total: number;
  entries: QueueEntry[];
}

export interface ReorderRequest {
  position: number;
  reason: string;
  justification: string;
}

// Mensagens que o servidor envia pelo WebSocket.
export type ServerMessage =
  | { type: "queue.snapshot"; snapshot: QueueSnapshot }
  | { type: "queue.patch"; total: number; entries: QueueEntry[]; removed?: string[] }
  | { type: "audit.appended"; entry: AuditEntry }
  | { type: "activity"; at: string; text: string };

export type ConnectionStatus = "connecting" | "open" | "closed";
