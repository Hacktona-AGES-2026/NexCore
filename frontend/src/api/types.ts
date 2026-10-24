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

export type HighlightKind = "urgency" | "events" | "symptoms" | "red_flag";

/** Trecho de texto livre que o Neco usou. `start`/`end` são índices no campo. */
export interface Highlight {
  field: "clinicalNote" | "regulationNote";
  start: number;
  end: number;
  kind: HighlightKind;
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
  highlights: Highlight[];
}

export type AuditKind = "recalc" | "intake" | "manual" | "validation" | "data";

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

// ---------- pendências de dados ----------
export type PendencyKind = "cid_flag" | "duplicate" | "biopsy" | "left_queue" | "orphan_event";

export interface Pendency {
  id: string;
  kind: PendencyKind;
  title: string;
  detail: string;
  /** Nome do paciente (ou id, quando a solicitação não está na fila). */
  name: string;
  entryIds: string[];
}

export interface ResolveRequest {
  action: string;
  note?: string;
}

// ---------- equidade ----------
export interface CityStat {
  name: string;
  lat: number;
  lon: number;
  total: number;
  avgWait: number;
  overdue: number;
  urgent: number;
  distanceKm: number | null;
}

export interface GroupStat {
  label: string;
  total: number;
  avgWait: number;
  overduePct: number;
}

export interface EquityReport {
  cities: CityStat[];
  byDistance: GroupStat[];
  byAge: GroupStat[];
  bySex: GroupStat[];
}

// ---------- resumo (telão) ----------
export interface QueueSummary {
  total: number;
  oncologic: number;
  overdueTotal: number;
  byClass: { cls: UrgencyClass; total: number; overdue: number }[];
  bySpecialty: { label: string; total: number; overdue: number }[];
  waitBuckets: { label: string; total: number }[];
  /** Topo da fila anonimizado (iniciais), próprio para tela pública. */
  top: { position: number; id: string; initials: string; procedure: string; cls: UrgencyClass; days: number }[];
}

// ---------- Pergunte ao Neco ----------
export interface AskRequest {
  question: string;
}

export interface NecoAnswer {
  text: string;
  /** Solicitações citadas, para o front virar links. */
  entryIds?: string[];
  suggestions?: string[];
}

// Mensagens que o servidor envia pelo WebSocket.
export type ServerMessage =
  | { type: "queue.snapshot"; snapshot: QueueSnapshot }
  | { type: "queue.patch"; total: number; entries: QueueEntry[]; removed?: string[] }
  | { type: "audit.appended"; entry: AuditEntry }
  | { type: "pendency.resolved"; id: string }
  | { type: "activity"; at: string; text: string };

export type ConnectionStatus = "connecting" | "open" | "closed";
