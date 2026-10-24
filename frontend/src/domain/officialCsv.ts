import type { QueueEntry } from "../api/types";
import { CLASS_LABEL, DEADLINE_DAYS, byPosition, isDpss } from "./queue";

const br = (n: number) => String(n).replace(".", ",");
const quote = (s: string) => `"${s.replace(/"/g, '""')}"`;

/** Mesmo texto de backend/app/regulation/impact.py `_dpss_text()`: como o índice foi composto. */
function indexText(e: QueueEntry, f: Record<string, number>): string {
  if (!isDpss(e) || !e.priority) {
    return `Índice ${e.score == null ? "—" : br(e.score)}/97 (urgência ${br(f.urgency)}, espera ${br(f.wait)}, eventos ${br(f.events)}, sintomas ${br(f.symptoms)}).`;
  }
  const p = e.priority;
  const band = p.protected ? "Faixa protegida (A1/A2 ou câncer), ordenada pelo DPSS. " : "";
  if (e.score == null) return band + "DPSS não calculado: classe SWALIS não inferida com segurança.";
  const social = p.socioeconomicVulnerability != null
    ? `, S=${br(Math.round(p.socioeconomicVulnerability * 1000) / 1000)} com peso ${br(p.socioeconomicWeight)}` : "";
  return band + `DPSS ${br(e.score)} = espera/prazo ${br(f.wait)} × (1 + fator clínico ${br(f.clinical)} + vulnerabilidade social ${br(f.social)}${social}).`;
}

/** Mesmo texto da justificativa de backend/app/regulation/impact.py, a partir de uma QueueEntry. */
export function justification(e: QueueEntry): string {
  const deadline = DEADLINE_DAYS[e.urgencyClass];
  const late = e.daysWaiting - deadline;
  const f = Object.fromEntries(e.factors.map((x) => [x.key, x.value]));
  const parts = [
    `Classe ${e.urgencyClass} (${CLASS_LABEL[e.urgencyClass]}, ${isDpss(e) ? "SWALIS inferido pelo DPS" : "SWALIS adaptado"}): ${e.classReason}.`,
    `Espera de ${e.daysWaiting} dias${late > 0 ? `, ${late} além do prazo de ${deadline}.` : `, dentro do prazo de ${deadline}.`}`,
    indexText(e, f),
    ...e.warnings.map((w) => w.text),
  ];
  if (e.locked) parts.push("Posição ajustada manualmente pela regulação; motivo no relatório de auditoria.");
  return parts.join(" ");
}

/** fila_priorizada.csv (solicitacao_id, posicao, justificativa) da fila como está agora. */
export function officialCsv(entries: QueueEntry[]): string {
  const rows = [...entries].sort(byPosition).map((e) => [e.id, e.position, quote(justification(e))].join(","));
  return ["solicitacao_id,posicao,justificativa", ...rows].join("\r\n") + "\r\n";
}
