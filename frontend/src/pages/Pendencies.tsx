import { useMemo, useState } from "react";
import type { Pendency } from "../api/types";
import { ChevronRight } from "../components/icons";
import { Neco } from "../components/Neco";
import { PendencyPanel, RISK_LABEL } from "../components/PendencyPanel";
import { useQueue } from "../state/QueueContext";

const RISK_ORDER = { alto: 0, medio: 1, baixo: 2 };

export function Pendencies() {
  const { pendencies } = useQueue();
  const [filter, setFilter] = useState("todas");
  const [openId, setOpenId] = useState<string | null>(null);

  // Os tipos vêm dos dados: um tipo novo de pendência aparece aqui sem mudar a tela.
  const kinds = useMemo(() => {
    const seen = new Map<string, { label: string; n: number }>();
    for (const p of pendencies) {
      const k = seen.get(p.kind) ?? { label: p.kindLabel, n: 0 };
      k.n++;
      seen.set(p.kind, k);
    }
    return [...seen.entries()];
  }, [pendencies]);
  const high = pendencies.filter((p) => p.risk === "alto").length;

  const list = useMemo(() => [...pendencies]
    .filter((p) => filter === "todas" || (filter === "alto" ? p.risk === "alto" : p.kind === filter))
    .sort((a, b) => RISK_ORDER[a.risk] - RISK_ORDER[b.risk] || a.id.localeCompare(b.id)), [pendencies, filter]);
  const open: Pendency | null = pendencies.find((p) => p.id === openId) ?? null;

  return (
    <section className="page">
      <div className="head">
        <div>
          <h1>Pendências de dados</h1>
          <p className="sub">Inconsistências que o Neco encontrou. Ele já contorna cada uma no cálculo, mas a correção é humana.</p>
        </div>
      </div>
      <p className="hint"><Neco size={20} />Ordenei por risco: primeiro as que podem estar escondendo um paciente grave.</p>
      <div className="bar">
        <div className="seg seg-scroll">
          <button className={filter === "todas" ? "on" : ""} onClick={() => setFilter("todas")}>Todas <span className="cnt">{pendencies.length}</span></button>
          <button className={filter === "alto" ? "on" : ""} onClick={() => setFilter("alto")}>Risco alto <span className="cnt">{high}</span></button>
          {kinds.map(([kind, k]) => (
            <button key={kind} className={filter === kind ? "on" : ""} onClick={() => setFilter(kind)}>{k.label} <span className="cnt">{k.n}</span></button>
          ))}
        </div>
      </div>
      <div className="card">
        {list.length ? list.map((p) => (
          <button className="pend-row" key={p.id} onClick={() => setOpenId(p.id)}>
            <span className={`risk-dot ${p.risk}`} title={RISK_LABEL[p.risk]} />
            <span className="pend-main">
              <b>{p.title}</b>
              <small>{p.name} · {p.divergences[0]?.values.map((v) => `${v.source}: ${v.value}`).join("  ≠  ")}</small>
            </span>
            <span className="kind-chip">{p.kindLabel}</span>
            <ChevronRight />
          </button>
        )) : <p className="empty">Nada pendente aqui.</p>}
      </div>
      <PendencyPanel pendency={open} onClose={() => setOpenId(null)} />
    </section>
  );
}
