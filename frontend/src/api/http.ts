import { ApiError, config, type Backend } from "./backend";
import type { ConnectionStatus, ImpactReport, ServerMessage } from "./types";

async function send(path: string, init?: RequestInit) {
  const res = await fetch(`${config.apiUrl}/hospitais/${config.hospitalId}${path}`, {
    ...init,
    // Só com corpo: um GET sem cabeçalhos extras não exige preflight de CORS.
    headers: init?.body ? { "Content-Type": "application/json", ...init.headers } : init?.headers,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(body.detail ?? `Erro ${res.status} em ${path}`, res.status);
  }
  return res;
}
const request = async <T,>(path: string, init?: RequestInit) => (await send(path, init)).json() as Promise<T>;
const missing = (err: unknown) => err instanceof ApiError && err.status === 404;

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
  getPendencies: () => request("/pendencias"),
  getEquity: () => request("/painel/equidade"),
  getSummary: () => request("/painel/resumo"),
  getExplanation: (id) => request(`/fila/${id}/explicacao`),
  getEquityInsight: () => request("/painel/equidade/comentario"),
  getImpactInsight: () => request("/painel/impacto/comentario"),
  // Enquanto o backend não tiver /painel/impacto, usa o relatório gerado por
  // entrega/gerar_entrega.py com o verificador oficial (mesmo dataset).
  getImpact: () => request<ImpactReport>("/painel/impacto").catch(async (err) => {
    if (!missing(err)) throw err;
    const ref = (await import("../mock/impacto.json")).default as ImpactReport;
    return { ...ref, source: "referencia" as const };
  }),
  // Sem /fila/exportar, a tela de Impacto monta o CSV a partir da fila ao vivo.
  exportQueueCsv: async () => (await send("/fila/exportar")).text(),
  reorder: (id, req) => request(`/fila/${id}/reordenar`, { method: "POST", body: JSON.stringify(req) }),
  validate: (id) => request(`/fila/${id}/validar`, { method: "POST" }),
  resolvePendency: (id, req) => request(`/pendencias/${id}/resolver`, { method: "POST", body: JSON.stringify(req) }),
  simulatePendency: (id, req) => request(`/pendencias/${id}/simular`, { method: "POST", body: JSON.stringify(req) }),
  ask: (req) => request("/neco/perguntar", { method: "POST", body: JSON.stringify(req) }),
  subscribe: openRealtime,
};
