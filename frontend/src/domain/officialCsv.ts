import type { QueueEntry } from "../api/types";
import { CLASS_LABEL, DEADLINE_DAYS, byPosition } from "./queue";

const br = (n: number) => String(n).replace(".", ",");
const quote = (s: string) => `"${s.replace(/"/g, '""')}"`;

/** Mesmo texto de entrega/neco.py `justificativa()`, a partir de uma QueueEntry. */
export function justification(e: QueueEntry): string {
  const deadline = DEADLINE_DAYS[e.urgencyClass];
  const late = e.daysWaiting - deadline;
  const f = Object.fromEntries(e.factors.map((x) => [x.key, x.value]));
  const parts = [
    `Classe ${e.urgencyClass} (${CLASS_LABEL[e.urgencyClass]}, SWALIS adaptado): ${e.classReason}.`,
    `Espera de ${e.daysWaiting} dias${late > 0 ? `, ${late} além do prazo de ${deadline}.` : `, dentro do prazo de ${deadline}.`}`,
    `Índice ${br(e.score)}/97 (urgência ${br(f.urgency)}, espera ${br(f.wait)}, eventos ${br(f.events)}, sintomas ${br(f.symptoms)}).`,
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
