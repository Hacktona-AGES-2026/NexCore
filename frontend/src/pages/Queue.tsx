import { useCallback, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import type { UrgencyClass } from "../api/types";
import { SearchIcon, ShieldIcon } from "../components/icons";
import { PatientDrawer } from "../components/PatientDrawer";
import { CLASS_LABEL, byPosition, daysOverdue, goldenRuleViolation } from "../domain/queue";
import { useQueue } from "../state/QueueContext";

const FILTERS: ("todas" | UrgencyClass)[] = ["todas", "A1", "A2", "B", "C", "D"];

export function Queue() {
  const { entries, total, deltas, loaded, backend } = useQueue();
  const { id } = useParams();
  const navigate = useNavigate();
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("todas");
  const [q, setQ] = useState("");
  const close = useCallback(() => navigate("/fila"), [navigate]);

  const rows = useMemo(() => {
    const term = q.trim().toLowerCase();
    return [...entries].sort(byPosition).filter((e) =>
      (filter === "todas" || e.urgencyClass === filter) &&
      (!term || `${e.name} ${e.id} ${e.cid} ${e.procedure}`.toLowerCase().includes(term)));
  }, [entries, filter, q]);
  const showGaps = filter === "todas" && !q;
  const ruleOk = !goldenRuleViolation(entries);

  const body: JSX.Element[] = [];
  let last = 0;
  for (const e of rows) {
    if (showGaps && e.position - last > 1) body.push(<tr key={`gap-${e.id}`} className="gap"><td colSpan={4}>{e.position - last - 1} solicitações</td></tr>);
    last = e.position;
    const d = deltas[e.id];
    const late = daysOverdue(e);
    body.push(
      <tr key={e.id} className={`row ${id === e.id ? "sel" : ""} ${d ? "moved" : ""}`} onClick={() => navigate(`/fila/${e.id}`)}>
        <td className="pos">
          {e.position}
          {!!d && <span className={`d ${e.locked ? "man" : d > 0 ? "up" : "down"}`}>{d > 0 ? "↑" : "↓"}{Math.abs(d)}</span>}
        </td>
        <td className="who"><b>{e.name}{e.warnings.length > 0 && <span className="flag" title="Precisa de revisão" />}</b><small>{e.procedure}</small></td>
        <td><span className={`cls ${e.urgencyClass}`}><i />{CLASS_LABEL[e.urgencyClass]}</span></td>
        <td className="hide-sm">{e.daysWaiting} dias{late > 0 && <><br /><span className="late">+{late} do prazo</span></>}</td>
      </tr>,
    );
  }
  if (showGaps && total - last > 0) body.push(<tr key="gap-end" className="gap"><td colSpan={4}>{total - last} solicitações</td></tr>);

  return (
    <section className="page">
      <div className="head">
        <div><h1>Fila priorizada</h1><p className="sub">Clique em um paciente para ver por que ele está nessa posição.</p></div>
        <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
          <span className={`rule ${ruleOk ? "" : "bad"}`}><ShieldIcon check={ruleOk} />{ruleOk ? "Regra de ouro ok" : "Regra de ouro violada"}</span>
          {backend.simulateEvent && <button className="btn" onClick={backend.simulateEvent}>Simular evento</button>}
        </div>
      </div>
      <div className="bar">
        <label className="search"><SearchIcon /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar paciente, solicitação ou CID" /></label>
        <div className="seg">
          {FILTERS.map((f) => <button key={f} className={filter === f ? "on" : ""} onClick={() => setFilter(f)}>{f === "todas" ? "Todas" : f}</button>)}
        </div>
      </div>
      <div className="card">
        <table>
          <thead><tr><th>Posição</th><th>Paciente</th><th>Urgência</th><th className="hide-sm">Espera</th></tr></thead>
          <tbody>{loaded ? (body.length ? body : <tr><td colSpan={4} className="empty">Nada encontrado.</td></tr>) : <tr><td colSpan={4} className="empty">Carregando a fila…</td></tr>}</tbody>
        </table>
      </div>
      <PatientDrawer entryId={id ?? null} onClose={close} />
    </section>
  );
}
