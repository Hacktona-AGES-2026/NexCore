// Respostas do "Pergunte ao Neco" no mock: intenções por palavra-chave.
// No backend real, um LLM com ferramentas de consulta à fila responde,
// sempre citando os dados e sem alterar a prioridade.
import type { EquityReport, NecoAnswer, Pendency, QueueEntry, QueueSummary } from "../api/types";
import { CLASS_LABEL, CLASS_RANK, DEADLINE_DAYS, byPosition, daysOverdue } from "../domain/queue";

const norm = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const SUGGESTIONS = [
  "Por que a Gabriela está na posição dela?",
  "Quem da ortopedia passou do prazo?",
  "Quantos casos A1 temos?",
  "Quem mora longe espera mais?",
];

function findPatients(q: string, entries: QueueEntry[]) {
  const text = norm(q);
  const words = new Set(text.split(/[^a-z]+/));
  // Nome completo vence; senão, casa pelo primeiro nome.
  const full = entries.filter((e) => text.includes(norm(e.name)));
  return full.length ? full : entries.filter((e) => words.has(norm(e.name.split(" ")[0])));
}

function explain(e: QueueEntry, sorted: QueueEntry[]) {
  const late = daysOverdue(e);
  const above = sorted[sorted.indexOf(e) - 1];
  let t = `${e.name} está na posição ${e.position} como ${CLASS_LABEL[e.urgencyClass]} (${e.urgencyClass}): ${e.classReason}. `;
  t += late > 0 ? `Espera há ${e.daysWaiting} dias, ${late} além do prazo de ${DEADLINE_DAYS[e.urgencyClass]}. ` : `Espera há ${e.daysWaiting} dias, dentro do prazo. `;
  if (above) t += CLASS_RANK[above.urgencyClass] > CLASS_RANK[e.urgencyClass] ? `Logo acima está ${above.name}, que é mais urgente.` : `Logo acima está ${above.name}, com índice ${above.score} contra ${e.score}.`;
  if (e.warnings.length) t += ` Atenção: ${e.warnings[0].text}`;
  return t;
}

export function answer(question: string, ctx: { entries: QueueEntry[]; summary: QueueSummary; equity: EquityReport; pendencies: Pendency[] }): NecoAnswer {
  const q = norm(question);
  const sorted = [...ctx.entries].sort(byPosition);
  const people = findPatients(question, sorted);

  if (people.length >= 2 && /acima|abaixo|frente|antes|depois|compar/.test(q)) {
    const [a, b] = people.sort(byPosition);
    const why = CLASS_RANK[a.urgencyClass] > CLASS_RANK[b.urgencyClass]
      ? `${a.name} é ${CLASS_LABEL[a.urgencyClass]} (${a.classReason}), enquanto ${b.name} é ${CLASS_LABEL[b.urgencyClass]} (${b.classReason}). A classe de urgência vem antes do índice.`
      : `Os dois são ${CLASS_LABEL[a.urgencyClass]}. ${a.name} tem índice ${a.score} e ${b.name} ${b.score}; a diferença vem principalmente de ${a.factors[1].value > b.factors[1].value ? "tempo de espera" : "eventos recentes"}.`;
    return { text: `${a.name} está na posição ${a.position} e ${b.name} na ${b.position}. ${why}`, entryIds: [a.id, b.id] };
  }
  if (people.length >= 1) return { text: explain(people[0], sorted), entryIds: [people[0].id] };

  const cls = q.match(/\b(a1|a2|b|c|d)\b/);
  if (/quant/.test(q) && cls) {
    const c = ctx.summary.byClass.find((x) => x.cls.toLowerCase() === cls[1])!;
    return { text: `Temos ${c.total} casos ${c.cls} (${CLASS_LABEL[c.cls]}). Deles, ${c.overdue} já passaram do prazo de ${DEADLINE_DAYS[c.cls]} dias.` };
  }
  if (/longe|distanc|interior|equidade|desigual|municip/.test(q)) {
    const [near, , far] = ctx.equity.byDistance;
    return {
      text: `Sim. Quem mora a mais de 200 km espera em média ${far.avgWait} dias, contra ${near.avgWait} de quem mora até 50 km. ${far.overduePct}% dos pacientes distantes já passaram do prazo, contra ${near.overduePct}% dos próximos. Vale olhar o painel de equidade.`,
      suggestions: ["Quantos casos A1 temos?"],
    };
  }
  if (/pendenc|dado|duplic|inconsist|cadastro/.test(q)) {
    const by = (k: Pendency["kind"]) => ctx.pendencies.filter((p) => p.kind === k).length;
    return { text: `Há ${ctx.pendencies.length} pendências de dados: ${by("cid_flag")} cadastros com câncer divergente do CID, ${by("duplicate")} possíveis duplicatas, ${by("biopsy")} biópsias positivas com CID benigno, ${by("left_queue")} pacientes que podem ter saído da fila e ${by("orphan_event")} eventos sem solicitação.` };
  }
  const spec = ctx.summary.bySpecialty.find((s) => q.includes(norm(s.label).slice(0, 6)));
  if (spec || /prazo|vencid|atras/.test(q)) {
    const list = sorted.filter((e) => daysOverdue(e) > 0 && (!spec || norm(e.specialty) === norm(spec.label))).slice(0, 5);
    const head = spec ? `${spec.label}: ${spec.overdue} de ${spec.total} pacientes passaram do prazo.` : `${ctx.summary.overdueTotal} de ${ctx.summary.total} pacientes passaram do prazo da sua classe.`;
    return { text: list.length ? `${head} Os primeiros da fila nessa situação:` : head, entryIds: list.map((e) => e.id) };
  }
  if (/cancer|oncolog|neoplas/.test(q)) {
    return { text: `Há ${ctx.summary.oncologic} pacientes com câncer pelo CID. Todos estão acima dos casos sem urgência, como manda a regra de ouro. Os primeiros:`, entryIds: sorted.filter((e) => e.oncologic).slice(0, 4).map((e) => e.id) };
  }
  return { text: "Não entendi essa pergunta. Posso explicar a posição de um paciente, comparar dois pacientes, contar casos por classe, listar quem passou do prazo ou falar de equidade e pendências.", suggestions: SUGGESTIONS };
}

export { SUGGESTIONS };
