// Backend simulado em memória. Imita o contrato REST + WebSocket para
// o front funcionar antes do servidor existir (VITE_USE_MOCK=true).
import type { Backend } from "../api/backend";
import type {
  AuditEntry, AuditKind, ClinicalEvent, ConnectionStatus, EquityReport, ImpactReport, Pendency, QueueEntry, QueueSummary, ScoreFactor,
  ServerMessage, UrgencyClass, Warning,
} from "../api/types";
import { CLASS_RANK, goldenRuleViolation, relocate } from "../domain/queue";
import { extractHighlights } from "./highlights";
import { answer } from "./neco";
import seed from "./seed.json";
import impact from "./impacto.json";
import stats from "./stats.json";

type SeedRow = (typeof seed.rows)[number];

const FACTOR_KEYS: ScoreFactor["key"][] = ["urgency", "wait", "events", "symptoms"];
const FACTOR_MAX = [40, 25, 20, 12];

function classReason(r: { urgencyClass: UrgencyClass; cid: string; oncologic: boolean; pain?: string; limitation?: string }) {
  const pain = Number(r.pain);
  switch (r.urgencyClass) {
    case "A1": return `câncer confirmado pelo CID ${r.cid} com piora recente`;
    case "A2": return r.oncologic ? `câncer confirmado pelo CID ${r.cid}` : `há biópsia positiva, embora o CID ${r.cid} ainda não indique câncer`;
    case "B":
      if (pain >= 7) return `dor intensa (${pain}/10)`;
      if (r.limitation === "grave") return "limitação funcional grave";
      if (/^D(3[7-9]|4[0-8])|^R91/.test(r.cid.replace(".", ""))) return "lesão de comportamento incerto";
      return "idas repetidas ao pronto-socorro";
    case "C":
      if (pain >= 4) return `dor moderada (${pain}/10)`;
      if (r.limitation === "moderada") return "limitação funcional moderada";
      return "uma ida recente ao pronto-socorro";
    default: return "sem dor, limitação ou piora relevantes";
  }
}

function toEntry(r: SeedRow): QueueEntry {
  const warnings: Warning[] = [];
  if (/^I20/.test(r.cid)) warnings.push({ level: "info", text: "Angina pode ser caso muito urgente. Não recebi eventos que confirmem; vale revisar." });
  if (r.alerts.some((a) => a.startsWith("Flag"))) warnings.push({ level: "info", text: `O cadastro marca câncer, mas o CID ${r.cid} não indica. Usei o CID.` });
  const entry: QueueEntry = {
    id: r.id, patientId: r.pac, name: r.nome, sex: r.sexo, age: r.idade, city: r.mun,
    procedure: r.proc, specialty: r.esp, cid: r.cid, cidDescription: r.cidd,
    asa: r.asa || undefined, comorbidities: r.com || undefined, pain: r.dor || undefined, limitation: r.lim || undefined,
    clinicalNote: r.just, regulationNote: r.obs || undefined, enteredAt: r.entrada, daysWaiting: r.dias,
    manualPriority: r.prio || undefined, oncologic: r.onco,
    position: r.pos, urgencyClass: r.classe as UrgencyClass, score: r.score,
    factors: r.mods.map((m, i) => ({ key: FACTOR_KEYS[i], value: m.v, max: FACTOR_MAX[i] })),
    classReason: "", warnings, locked: false, pendingConfirmation: false,
    events: r.eventos.map((e) => ({ date: e.d, type: e.t, result: e.r, value: e.v || undefined, description: e.desc, origin: e.o })),
    highlights: extractHighlights(r.just, r.obs || undefined),
  };
  entry.classReason = classReason(entry);
  // Sinal de gravidade só no texto livre de um caso que não está no topo: vale revisão.
  const flag = entry.highlights.find((h) => h.kind === "red_flag");
  if (flag && CLASS_RANK[entry.urgencyClass] <= 3) {
    const src = flag.field === "clinicalNote" ? entry.clinicalNote : entry.regulationNote!;
    warnings.unshift({ level: "info", text: `O texto cita "${src.slice(flag.start, flag.end).toLowerCase()}", sinal de gravidade que não está nos campos estruturados.` });
  }
  return entry;
}

function fnv(s: string) {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193); }
  return (h >>> 0).toString(16).padStart(8, "0");
}

const today = (hh: number, mm: number) => { const d = new Date(); d.setHours(hh, mm, 0, 0); return d.toISOString(); };
const ADMIN = "Marina Albuquerque";

export function createMockBackend(): Backend {
  let entries = seed.rows.map(toEntry);
  let total = seed.total;
  const audit: AuditEntry[] = [];
  const listeners = new Set<(m: ServerMessage) => void>();
  const emit = (m: ServerMessage) => setTimeout(() => listeners.forEach((l) => l(m)), 120);

  function appendAudit(a: { kind: AuditKind; author: string; entry: { id: string; name: string }; from: number | null; to: number; justification: string; at?: string }) {
    const prevHash = audit[0]?.hash ?? "00000000";
    const at = a.at ?? new Date().toISOString();
    const rec: AuditEntry = {
      id: `AUD-${String(audit.length + 1).padStart(5, "0")}`, at, author: a.author, kind: a.kind,
      entryId: a.entry.id, entryName: a.entry.name, from: a.from, to: a.to, justification: a.justification,
      prevHash, hash: fnv(prevHash + JSON.stringify([at, a.author, a.kind, a.entry.id, a.from, a.to, a.justification])),
    };
    audit.unshift(rec);
    return rec;
  }

  // histórico de exemplo
  const sorted = () => [...entries].sort((a, b) => a.position - b.position);
  const s = sorted();
  appendAudit({ kind: "intake", author: "Neco", entry: { id: "LOTE-0001", name: "Carga inicial" }, from: null, to: 941, at: today(6, 2),
    justification: "941 solicitações recebidas e priorizadas. 44 marcações de câncer do cadastro não batiam com o CID; usei o CID." });
  appendAudit({ kind: "recalc", author: "Neco", entry: s[2], from: 5, to: 3, at: today(6, 12), justification: "Tomografia com progressão da doença." });

  const changed = (before: QueueEntry[]) => entries.filter((e) => !before.includes(e));

  // Move pela regra do Neco: atrás do último com classe mais urgente ou índice maior.
  function necoPlace(target: QueueEntry) {
    let prev: QueueEntry | undefined;
    for (const o of sorted()) if (o.id !== target.id && (CLASS_RANK[o.urgencyClass] > CLASS_RANK[target.urgencyClass] || (CLASS_RANK[o.urgencyClass] === CLASS_RANK[target.urgencyClass] && (o.score ?? -Infinity) >= (target.score ?? -Infinity)))) prev = o;
    let to = prev ? prev.position + 1 : 1;
    if (to > target.position) to--;
    return to;
  }

  function update(id: string, patch: Partial<QueueEntry>, event?: ClinicalEvent) {
    entries = entries.map((e) => e.id === id ? { ...e, ...patch, events: event ? [...e.events, event] : e.events } : e);
    return entries.find((e) => e.id === id)!;
  }

  const script: (() => void)[] = [
    () => {
      const t = entries.find((e) => e.cid === "K80.2"); if (!t) return;
      const from = t.position;
      const factors = t.factors.map((f) => f.key === "urgency" ? { ...f, value: 22 } : f.key === "wait" ? { ...f, value: 25 } : f.key === "events" ? { ...f, value: 10 } : f);
      const u = update(t.id, { urgencyClass: "B", factors, score: +factors.reduce((a, f) => a + f.value, 0).toFixed(1), classReason: "ida ao pronto-socorro com suspeita de colecistite aguda" },
        { date: "2026-10-23", type: "pronto_socorro", result: "observacao", description: "Dor em hipocôndrio direito, suspeita de colecistite aguda.", origin: "PS Hospital Sao Lucas" });
      const before = entries;
      entries = relocate(entries, u.id, necoPlace(u));
      const to = entries.find((e) => e.id === u.id)!.position;
      emit({ type: "queue.patch", total, entries: changed(before) });
      emit({ type: "audit.appended", entry: appendAudit({ kind: "recalc", author: "Neco", entry: u, from, to, justification: "Pronto-socorro hoje com suspeita de colecistite aguda. Reclassificado de Moderado (C) para Prioritário (B)." }) });
      emit({ type: "activity", at: new Date().toISOString(), text: `${u.name.split(" ")[0]} subiu de ${from} para ${to} após ida ao PS` });
    },
    () => {
      const to = sorted().filter((e) => e.urgencyClass === "A2").pop()!.position + 1;
      const before = entries;
      entries = entries.map((e) => e.position >= to ? { ...e, previousPosition: e.position, position: e.position + 1 } : e);
      const fresh: QueueEntry = {
        id: "SOL-2026-00942", patientId: "PAC-00901", name: "Rosa Maria Dutra", sex: "F", age: 58, city: "Canoas",
        procedure: "Mastectomia / setorectomia de mama", specialty: "Mastologia", cid: "C50.9", cidDescription: "Neoplasia maligna da mama",
        asa: "2", comorbidities: "HAS", pain: "3", limitation: "leve", clinicalNote: "Nódulo em mama esquerda, core biopsy com carcinoma ductal invasivo.",
        enteredAt: "2026-10-23", daysWaiting: 0, oncologic: true, position: to, urgencyClass: "A2", score: 37.4,
        factors: [{ key: "urgency", value: 34, max: 40 }, { key: "wait", value: 0, max: 25 }, { key: "events", value: 0, max: 20 }, { key: "symptoms", value: 3.4, max: 12 }],
        classReason: "câncer confirmado pelo CID C50.9", warnings: [], locked: false, pendingConfirmation: false,
        events: [{ date: "2026-10-15", type: "biopsia", result: "positivo", description: "Carcinoma ductal invasivo grau 2.", origin: "patologia" }],
        highlights: extractHighlights("Nódulo em mama esquerda, core biopsy com carcinoma ductal invasivo."),
      };
      entries = [...entries, fresh]; total++;
      emit({ type: "queue.patch", total, entries: changed(before) });
      emit({ type: "audit.appended", entry: appendAudit({ kind: "intake", author: "Neco", entry: fresh, from: null, to, justification: "Nova entrada com câncer de mama confirmado por biópsia. Classificada como Urgente (A2), acima de todos os casos sem câncer." }) });
      emit({ type: "activity", at: new Date().toISOString(), text: `Nova entrada: Rosa na posição ${to}` });
    },
    () => {
      const t = entries.find((e) => e.cid === "K40.9"); if (!t) return;
      const u = update(t.id, { pendingConfirmation: true, warnings: [{ level: "critical", text: "Call center informou cirurgia em outro serviço. Confirme antes de retirar da fila." }, ...t.warnings] },
        { date: "2026-10-23", type: "contato_telefonico", result: "informou_cirurgia_outro_servico", description: "Familiar informa que paciente operou em hospital privado.", origin: "call center" });
      emit({ type: "queue.patch", total, entries: [u] });
      emit({ type: "audit.appended", entry: appendAudit({ kind: "recalc", author: "Neco", entry: u, from: u.position, to: u.position, justification: "Informou cirurgia em outro serviço. Posição mantida até confirmação humana: o Neco não retira pacientes da fila." }) });
      emit({ type: "activity", at: new Date().toISOString(), text: `${u.name.split(" ")[0]} pode ter operado em outro serviço` });
    },
  ];
  let step = 0;
  let pendencies = stats.pendencies as unknown as Pendency[];
  const equity = { cities: stats.cities, byDistance: stats.byDistance, byAge: stats.byAge, bySex: stats.bySex } as EquityReport;
  // O resumo do mock vem do dataset inteiro (stats.json); as mudanças da amostra
  // (reclassificação, entrada nova, saída) são somadas por cima, para o telão acompanhar.
  const counts = (list: QueueEntry[]) => {
    const byClass = Object.fromEntries((["A1", "A2", "B", "C", "D"] as UrgencyClass[]).map((c) => [c, { total: 0, overdue: 0 }]));
    const buckets = [0, 0, 0, 0, 0];
    let onco = 0, overdue = 0;
    for (const e of list) {
      const late = e.daysWaiting > { A1: 15, A2: 21, B: 60, C: 180, D: 360 }[e.urgencyClass];
      byClass[e.urgencyClass].total++;
      if (late) { byClass[e.urgencyClass].overdue++; overdue++; }
      if (e.oncologic) onco++;
      const d = e.daysWaiting;
      buckets[d <= 90 ? 0 : d <= 180 ? 1 : d <= 365 ? 2 : d <= 730 ? 3 : 4]++;
    }
    return { byClass, buckets, onco, overdue };
  };
  const baseline = counts(entries);
  const summary = (): QueueSummary => {
    const base = stats.summary as QueueSummary;
    const now = counts(entries);
    return {
      ...base,
      total,
      oncologic: base.oncologic + now.onco - baseline.onco,
      overdueTotal: base.overdueTotal + now.overdue - baseline.overdue,
      byClass: base.byClass.map((c) => ({
        ...c,
        total: c.total + now.byClass[c.cls].total - baseline.byClass[c.cls].total,
        overdue: c.overdue + now.byClass[c.cls].overdue - baseline.byClass[c.cls].overdue,
      })),
      waitBuckets: base.waitBuckets.map((b, i) => ({ ...b, total: b.total + now.buckets[i] - baseline.buckets[i] })),
    };
  };

  // O mock registra a decisão, mas não recalcula a fila: a correção de verdade é do backend.
  const PENDENCY_LOG: Record<string, (v: Record<string, string>) => string> = {
    fix_cadastro: () => "Cadastro corrigido para bater com o CID.",
    update_cid: (v) => `CID corrigido para ${(v.cid ?? "").toUpperCase()}.`,
    keep: () => "Conferido e mantido como está.",
    unrelated: () => "Biópsia desconsiderada para esta solicitação.",
    merge: (v) => `Solicitações duplicadas mescladas; mantida a ${v.keep}.`,
    keep_both: () => "Conferido: são solicitações distintas.",
    remove: (v) => `Saída da fila confirmada (${v.confirmacao}).`,
    link: (v) => `Evento vinculado à solicitação ${v.target}.`,
    archive: () => "Evento arquivado: solicitação não está na fila.",
  };
  const fieldValues = (p: Pendency, actionId: string, values: Record<string, string> = {}) => {
    const action = p.actions.find((a) => a.id === actionId);
    if (!action) throw new Error(`A ação '${actionId}' não se aplica a esta pendência.`);
    const out: Record<string, string> = {};
    for (const f of action.fields) {
      out[f.name] = (values[f.name] || f.suggested || "").trim();
      if (f.required && !out[f.name]) throw new Error(`Preencha o campo '${f.label}'.`);
    }
    return { action, values: out };
  };

  const api: Backend = {
    getQueue: async () => ({ hospitalId: "hsl", total, entries: sorted() }),
    getAudit: async () => [...audit],
    getPendencies: async () => [...pendencies],
    getEquity: async () => equity,
    getSummary: async () => summary(),
    // O mock não tem modelo: responde "regras" com uma pequena espera, como faria o servidor.
    // Texto vazio = o front usa a explicação local.
    getExplanation: async () => {
      await new Promise((r) => setTimeout(r, 600));
      return { text: "", points: [], source: "regras" as const, verified: true };
    },
    getEquityInsight: async () => {
      await new Promise((r) => setTimeout(r, 900));
      const [near, , far] = equity.byDistance;
      return {
        text: `Quem mora a mais de 200 km espera em média ${far.avgWait - near.avgWait} dias a mais (${far.avgWait} contra ${near.avgWait}), e ${far.overduePct}% já passaram do prazo. A prioridade clínica não usa a distância, então essa diferença vem do acesso e merece atenção da gestão.`,
        source: "regras" as const, verified: true,
      };
    },
    getImpactInsight: async () => {
      await new Promise((r) => setTimeout(r, 900));
      const { headline: h, verifier: v } = impact as ImpactReport;
      return {
        text: `Dos ${h.a1Total} casos mais graves (câncer com piora recente), a regulação tinha marcado ${h.a1Low} como prioridade baixa ou vazia. Ao mesmo tempo, ${h.dHigh} casos sem urgência ocupavam prioridade alta. Na fila de hoje, ${v.manual.violacoes} pacientes com câncer ficam atrás de quem não tem urgência; na do Neco, ${v.neco.violacoes}.`,
        source: "regras" as const, verified: true,
      };
    },
    getImpact: async () => impact as ImpactReport,
    // Carregado só quando pedido: o CSV oficial tem as 941 justificativas.
    exportQueueCsv: async () => (await import("./fila_priorizada.csv?raw")).default,
    async simulatePendency(id, req) {
      const p = pendencies.find((x) => x.id === id);
      if (!p) throw new Error("Pendência não encontrada");
      const { action } = fieldValues(p, req.action, req.values);
      await new Promise((r) => setTimeout(r, 400));
      return {
        action: action.id, changes: [],
        summary: action.changesQueue
          ? "No modo de demonstração a fila não é recalculada; com o backend real esta prévia mostra a nova posição."
          : "Nenhuma mudança na fila: só o registro é corrigido.",
      };
    },
    async resolvePendency(id, req) {
      const p = pendencies.find((x) => x.id === id);
      if (!p) throw new Error("Pendência não encontrada");
      const { values } = fieldValues(p, req.action, req.values);
      pendencies = pendencies.filter((x) => x.id !== id);
      const outcome = PENDENCY_LOG[req.action]?.(values) ?? req.action;
      const rec = appendAudit({ kind: "data", author: ADMIN, entry: { id: p.entryIds[0] ?? p.id, name: p.name }, from: null, to: 0,
        justification: `${p.title}. ${outcome}${req.note ? " " + req.note : ""}` });
      emit({ type: "pendency.resolved", id });
      emit({ type: "audit.appended", entry: rec });
      return rec;
    },
    async ask(req) {
      await new Promise((r) => setTimeout(r, 500));
      return answer(req.question, { entries, summary: summary(), equity, pendencies });
    },
    async reorder(id, req) {
      const t = entries.find((e) => e.id === id);
      if (!t) throw new Error("Solicitação não encontrada");
      if (req.justification.trim().length < 40) throw new Error("Justificativa muito curta");
      const next = relocate(entries, id, req.position);
      const v = goldenRuleViolation(next);
      if (v) throw new Error(`${v.oncologic.name} tem câncer e ficaria atrás de quem não tem urgência.`);
      const before = entries;
      entries = next.map((e) => (e.id === id ? { ...e, locked: true } : e));
      const rec = appendAudit({ kind: "manual", author: ADMIN, entry: t, from: t.position, to: req.position, justification: `${req.reason}. ${req.justification.trim()}` });
      emit({ type: "queue.patch", total, entries: changed(before) });
      emit({ type: "audit.appended", entry: rec });
      emit({ type: "activity", at: rec.at, text: `Você moveu ${t.name.split(" ")[0]} de ${t.position} para ${req.position}` });
      return rec;
    },
    async validate(id) {
      const t = entries.find((e) => e.id === id)!;
      const rec = appendAudit({ kind: "validation", author: ADMIN, entry: t, from: t.position, to: t.position, justification: "Justificativa do Neco revisada e considerada plausível." });
      emit({ type: "audit.appended", entry: rec });
      return rec;
    },
    subscribe(onMessage, onStatus: (s: ConnectionStatus) => void) {
      listeners.add(onMessage);
      onStatus("connecting");
      const t = setTimeout(() => {
        onStatus("open");
        onMessage({ type: "queue.snapshot", snapshot: { hospitalId: "hsl", total, entries: sorted() } });
      }, 200);
      return () => { clearTimeout(t); listeners.delete(onMessage); onStatus("closed"); };
    },
    simulateEvent() {
      if (step < script.length) script[step++]();
      else emit({ type: "activity", at: new Date().toISOString(), text: "Nenhum evento novo na API" });
    },
  };

  // Cada aba tem seu próprio mock. Para o telão (outra janela) acompanhar a
  // demonstração, as ações que mudam estado são repetidas nas outras abas.
  if (typeof BroadcastChannel === "undefined") return api;
  const channel = new BroadcastChannel("nexcore-mock");
  type Op = { op: "simulate" } | { op: "reorder" | "validate" | "resolve"; id: string; req?: unknown };
  channel.onmessage = (ev: MessageEvent<Op>) => {
    const m = ev.data;
    if (m.op === "simulate") api.simulateEvent!();
    else if (m.op === "reorder") api.reorder(m.id, m.req as never).catch(() => {});
    else if (m.op === "validate") api.validate(m.id).catch(() => {});
    else api.resolvePendency(m.id, m.req as never).catch(() => {});
  };
  return {
    ...api,
    simulateEvent: () => { api.simulateEvent!(); channel.postMessage({ op: "simulate" }); },
    reorder: async (id, req) => { const r = await api.reorder(id, req); channel.postMessage({ op: "reorder", id, req }); return r; },
    validate: async (id) => { const r = await api.validate(id); channel.postMessage({ op: "validate", id }); return r; },
    resolvePendency: async (id, req) => { const r = await api.resolvePendency(id, req); channel.postMessage({ op: "resolve", id, req }); return r; },
  };
}
