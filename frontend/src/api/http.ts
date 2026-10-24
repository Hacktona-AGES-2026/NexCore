import { config, type Backend } from "./backend";
import type { ConnectionStatus, ServerMessage } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${config.apiUrl}/hospitais/${config.hospitalId}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Erro ${res.status} em ${path}`);
  }
  return res.json() as Promise<T>;
}

/**
 * WebSocket com reconexão (backoff exponencial até 15 s).
 * A cada conexão o servidor manda um `queue.snapshot`, então o front
 * se ressincroniza sozinho depois de uma queda.
 */
function openRealtime(onMessage: (m: ServerMessage) => void, onStatus: (s: ConnectionStatus) => void) {
  let ws: WebSocket | null = null;
  let attempt = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let closed = false;

  const connect = () => {
    onStatus("connecting");
    ws = new WebSocket(`${config.wsUrl}?hospital=${config.hospitalId}`);
    ws.onopen = () => {
      attempt = 0;
      onStatus("open");
    };
    ws.onmessage = (ev) => {
      try {
        onMessage(JSON.parse(ev.data) as ServerMessage);
      } catch {
        console.warn("Mensagem inválida do servidor", ev.data);
      }
    };
    ws.onclose = () => {
      onStatus("closed");
      if (closed) return;
      timer = setTimeout(connect, Math.min(15000, 500 * 2 ** attempt++));
    };
  };

  connect();
  return () => {
    closed = true;
    clearTimeout(timer);
    ws?.close();
  };
}

export const httpBackend: Backend = {
  getQueue: () => request("/fila"),
  getAudit: () => request("/auditoria"),
  reorder: (id, req) => request(`/fila/${id}/reordenar`, { method: "POST", body: JSON.stringify(req) }),
  validate: (id) => request(`/fila/${id}/validar`, { method: "POST" }),
  subscribe: openRealtime,
};
