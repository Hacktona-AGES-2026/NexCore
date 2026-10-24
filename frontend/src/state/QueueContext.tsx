import { createContext, useContext, useEffect, useMemo, useReducer, type ReactNode } from "react";
import { config, type Backend } from "../api/backend";
import { httpBackend } from "../api/http";
import type { AuditEntry, ConnectionStatus, QueueEntry, ServerMessage } from "../api/types";
import { createMockBackend } from "../mock/mockBackend";

interface Activity { at: string; text: string }

interface State {
  status: ConnectionStatus;
  loaded: boolean;
  total: number;
  entries: QueueEntry[];
  /** Variação de posição da última atualização, por solicitação. */
  deltas: Record<string, number>;
  audit: AuditEntry[];
  activity: Activity[];
}

type Action =
  | { type: "status"; status: ConnectionStatus }
  | { type: "audit.loaded"; audit: AuditEntry[] }
  | { type: "message"; message: ServerMessage };

const initial: State = { status: "connecting", loaded: false, total: 0, entries: [], deltas: {}, audit: [], activity: [] };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "status":
      return { ...state, status: action.status };
    case "audit.loaded":
      return { ...state, audit: action.audit };
    case "message": {
      const m = action.message;
      switch (m.type) {
        case "queue.snapshot":
          return {
            ...state, loaded: true, total: m.snapshot.total, entries: m.snapshot.entries, deltas: {},
            activity: state.loaded ? state.activity : [{ at: new Date().toISOString(), text: `Fila carregada com ${m.snapshot.total} solicitações` }],
          };
        case "queue.patch": {
          const byId = new Map(state.entries.map((e) => [e.id, e]));
          const deltas: Record<string, number> = {};
          for (const e of m.entries) {
            const old = byId.get(e.id);
            if (old && old.position !== e.position) deltas[e.id] = old.position - e.position;
            byId.set(e.id, e);
          }
          m.removed?.forEach((id) => byId.delete(id));
          return { ...state, total: m.total, entries: [...byId.values()], deltas };
        }
        case "audit.appended":
          return state.audit.some((a) => a.id === m.entry.id) ? state : { ...state, audit: [m.entry, ...state.audit] };
        case "activity":
          return { ...state, activity: [{ at: m.at, text: m.text }, ...state.activity].slice(0, 20) };
      }
    }
  }
  return state;
}

interface Ctx extends State {
  backend: Backend;
  entry: (id: string) => QueueEntry | undefined;
}

const QueueContext = createContext<Ctx | null>(null);

export function QueueProvider({ children }: { children: ReactNode }) {
  const backend = useMemo(() => (config.useMock ? createMockBackend() : httpBackend), []);
  const [state, dispatch] = useReducer(reducer, initial);

  useEffect(() => {
    backend.getAudit().then((audit) => dispatch({ type: "audit.loaded", audit })).catch(console.error);
    return backend.subscribe(
      (message) => dispatch({ type: "message", message }),
      (status) => dispatch({ type: "status", status }),
    );
  }, [backend]);

  const value = useMemo<Ctx>(
    () => ({ ...state, backend, entry: (id) => state.entries.find((e) => e.id === id) }),
    [state, backend],
  );
  return <QueueContext.Provider value={value}>{children}</QueueContext.Provider>;
}

export function useQueue() {
  const ctx = useContext(QueueContext);
  if (!ctx) throw new Error("useQueue fora do QueueProvider");
  return ctx;
}

/** Casos que o Neco marcou para revisão e ninguém validou ou moveu ainda. */
export function useReviewList() {
  const { entries, audit } = useQueue();
  return useMemo(() => {
    const handled = new Set(audit.filter((a) => a.kind === "validation" || a.kind === "manual").map((a) => a.entryId));
    return entries.filter((e) => e.warnings.length > 0 && !handled.has(e.id)).sort((a, b) => a.position - b.position);
  }, [entries, audit]);
}
