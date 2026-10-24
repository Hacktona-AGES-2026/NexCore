import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ChevronRight } from "../components/icons";
import { Neco } from "../components/Neco";
import { useQueue, useReviewList } from "../state/QueueContext";

const hhmm = (iso: string) => new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });

export function Home() {
  const { total, entries, activity, backend, patches } = useQueue();
  const review = useReviewList();
  const navigate = useNavigate();
  const [a1, setA1] = useState<number | null>(null);
  // A contagem por classe vem do resumo do servidor (a fila do mock é só uma amostra).
  useEffect(() => {
    backend.getSummary().then((s) => setA1(s.byClass.find((c) => c.cls === "A1")?.total ?? null)).catch(console.error);
  }, [backend, total]);
  const urgent = a1 ?? entries.filter((e) => e.urgencyClass === "A1").length;

  return (
    <section className="page">
      <div className="greet">
        <Neco size={88} analyze={patches} />
        <div>
          <h1>Bom dia, Marina</h1>
          <p>{review.length ? `A fila está atualizada. Separei ${review.length} ${review.length === 1 ? "caso" : "casos"} em que vale a sua revisão.` : "A fila está atualizada e não há casos pendentes de revisão."}</p>
        </div>
      </div>

      <div className="stats">
        <div className="card stat"><span>Na fila</span><b>{total}</b></div>
        <div className="card stat"><span>Urgentes (A1)</span><b>{urgent}</b></div>
        <div className="card stat accent"><span>Para revisar</span><b>{review.length}</b></div>
      </div>

      <div className="cols">
        <div className="card">
          <div className="list-h"><h2>Precisam da sua revisão</h2><Link className="link" to="/fila">Ver fila</Link></div>
          {review.length ? review.slice(0, 5).map((e) => (
            <button key={e.id} className="item" onClick={() => navigate(`/fila/${e.id}`)}>
              <Neco size={28} />
              <span><b>{e.name}</b><small>Posição {e.position} · {e.warnings[0].text}</small></span>
              <ChevronRight />
            </button>
          )) : <p className="empty">Tudo revisado.</p>}
        </div>
        <div className="card">
          <div className="list-h">
            <h2>Atividade</h2>
            {backend.simulateEvent && <button className="link" onClick={backend.simulateEvent}>Simular evento</button>}
          </div>
          <ul className="act">
            {activity.slice(0, 6).map((a, i) => <li key={a.at + a.text} className={i === 0 ? "new" : ""}><time>{hhmm(a.at)}</time><span>{a.text}</span></li>)}
          </ul>
        </div>
      </div>
    </section>
  );
}
