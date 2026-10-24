import type { QueueEntry, UrgencyClass } from "../api/types";

export const DEADLINE_DAYS: Record<UrgencyClass, number> = { A1: 15, A2: 21, B: 60, C: 180, D: 360 };
export const CLASS_RANK: Record<UrgencyClass, number> = { A1: 5, A2: 4, B: 3, C: 2, D: 1 };
export const CLASS_LABEL: Record<UrgencyClass, string> = {
  A1: "Muito urgente",
  A2: "Urgente",
  B: "Prioritário",
  C: "Moderado",
  D: "Eletivo",
};
export const FACTOR_LABEL = {
  urgency: "Urgência clínica",
  wait: "Tempo de espera",
  events: "Eventos recentes",
  symptoms: "Dor e limitação",
} as const;

export const byPosition = (a: QueueEntry, b: QueueEntry) => a.position - b.position;
export const daysOverdue = (e: QueueEntry) => e.daysWaiting - DEADLINE_DAYS[e.urgencyClass];
export const firstName = (name: string) => name.split(" ")[0];

/** Move uma entrada para outra posição, deslocando as demais. Retorna novas cópias. */
export function relocate(entries: QueueEntry[], id: string, to: number): QueueEntry[] {
  const target = entries.find((e) => e.id === id);
  if (!target) return entries;
  const from = target.position;
  return entries.map((e) => {
    if (e.id === id) return { ...e, previousPosition: from, position: to };
    let p = e.position;
    if (p > from) p--;
    if (p >= to) p++;
    return p === e.position ? e : { ...e, previousPosition: e.position, position: p };
  });
}

/** Regra de ouro: nenhum CID C abaixo de alguém sem urgência clínica (classe D). */
export function goldenRuleViolation(entries: QueueEntry[]) {
  const sorted = [...entries].sort(byPosition);
  let firstElective: QueueEntry | undefined;
  for (const e of sorted) {
    if (e.urgencyClass === "D" && !firstElective) firstElective = e;
    if (e.oncologic && firstElective) return { oncologic: e, elective: firstElective };
  }
  return null;
}
