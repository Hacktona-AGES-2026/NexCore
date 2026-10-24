import { useEffect, useState } from "react";
import type { EquityReport, QueueSummary } from "../api/types";
import { Neco } from "../components/Neco";
import { RSMap } from "../components/RSMap";
import { CLASS_LABEL } from "../domain/queue";
import { useQueue } from "../state/QueueContext";

function useClock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 1000 * 15); return () => clearInterval(t); }, []);
  return now;
}
const hhmm = (d: Date | string) => new Date(d).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });

/** Telão para TV do hospital: sem nomes completos, sem interação, legível de longe. */
export function Screen() {
  const { backend, total, status, activity } = useQueue();
  const [summary, setSummary] = useState<QueueSummary | null>(null);
  const [equity, setEquity] = useState<EquityReport | null>(null);
  const now = useClock();

  useEffect(() => {
    backend.getSummary().then(setSummary).catch(console.error);
    backend.getEquity().then(setEquity).catch(console.error);
  }, [backend]);
  if (!summary || !equity) return <div className="tv"><p className="empty">Carregando…</p></div>;

  const maxClass = Math.max(...summary.byClass.map((c) => c.total));
  const maxBucket = Math.max(...summary.waitBuckets.map((b) => b.total));
  const overduePct = Math.round((summary.overdueTotal / summary.total) * 100);
  const a1 = summary.byClass.find((c) => c.cls === "A1")!;

  return (
    <div className="tv">
      <header className="tv-h">
        <Neco size={44} invert />
        <div><b>Fila cirúrgica</b><span>Hospital São Lucas · priorizada pelo Neco</span></div>
        <div className={`tv-live ${status}`}><i />{status === "open" ? "Ao vivo" : "Reconectando"}</div>
        <time>{hhmm(now)}</time>
        <button className="tv-fs" onClick={() => document.documentElement.requestFullscreen?.()} title="Tela cheia">⛶</button>
      </header>

      <div className="tv-kpis">
        <div><span>Na fila</span><b>{total || summary.total}</b></div>
        <div><span>Muito urgentes (A1)</span><b>{a1.total}</b></div>
        <div><span>Passaram do prazo</span><b>{overduePct}%</b></div>
        <div><span>Câncer pelo CID</span><b>{summary.oncologic}</b></div>
      </div>

      <div className="tv-grid">
        <section className="tv-card">
          <h2>Topo da fila</h2>
          <ol className="tv-top">
            {summary.top.slice(0, 8).map((t) => (
              <li key={t.id}>
                <span className="p">{t.position}</span>
                <span className="n"><b>{t.initials}</b><small>{t.procedure}</small></span>
                <span className={`chip ${t.cls}`}>{t.cls}</span>
                <span className="d">{t.days} d</span>
              </li>
            ))}
          </ol>
          <p className="tv-foot">Pacientes identificados só por iniciais.</p>
        </section>

        <section className="tv-card">
          <h2>Por urgência</h2>
          <div className="tv-bars">
            {summary.byClass.map((c) => (
              <div className="tv-bar" key={c.cls}>
                <span className="l"><b>{c.cls}</b> {CLASS_LABEL[c.cls]}</span>
                <div className="tv-track">
                  <i className="late" style={{ width: `${(c.overdue / maxClass) * 100}%` }} />
                  <i className="ok" style={{ width: `${((c.total - c.overdue) / maxClass) * 100}%` }} />
                </div>
                <span className="v">{c.total}</span>
              </div>
            ))}
          </div>
          <div className="tv-key"><span><i className="late" />Passou do prazo</span><span><i className="ok" />No prazo</span></div>

          <h2 style={{ marginTop: "2.2vh" }}>Tempo de espera</h2>
          <div className="tv-hist">
            {summary.waitBuckets.map((b) => (
              <div key={b.label}>
                <span className="v">{b.total}</span>
                <i style={{ height: `${(b.total / maxBucket) * 100}%` }} />
                <span className="l">{b.label}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="tv-card tv-right">
          <h2>De onde vêm os pacientes</h2>
          <div className="tv-map"><RSMap cities={equity.cities} big /></div>
          <h2>Agora</h2>
          <ul className="tv-feed">
            {activity.slice(0, 4).map((a, i) => <li key={a.at + a.text} className={i === 0 ? "new" : ""}><time>{hhmm(a.at)}</time>{a.text}</li>)}
          </ul>
        </section>
      </div>
    </div>
  );
}
