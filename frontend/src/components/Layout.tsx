import { NavLink, Outlet } from "react-router-dom";
import { useQueue } from "../state/QueueContext";
import { ChevronDown, HomeIcon, ListIcon, ShieldIcon } from "./icons";
import { Neco } from "./Neco";

const STATUS_LABEL = { connecting: "Conectando", open: "Tempo real", closed: "Reconectando" };

export function Layout() {
  const { total, status } = useQueue();
  return (
    <div className="app">
      <aside className="side">
        <div className="brand"><Neco size={28} invert /><span>NexCore</span></div>
        <button className="hosp" title="Trocar hospital">Hospital São Lucas <ChevronDown /></button>
        <nav className="nav">
          <NavLink to="/" end><HomeIcon />Início</NavLink>
          <NavLink to="/fila"><ListIcon />Fila<span className="n">{total || ""}</span></NavLink>
          <NavLink to="/auditoria"><ShieldIcon />Auditoria</NavLink>
        </nav>
        <div className={`conn ${status}`}><i />{STATUS_LABEL[status]}</div>
        <div className="me" style={{ marginTop: 0 }}>
          <div className="av">MA</div>
          <div>Marina Albuquerque<small>Regulação</small></div>
        </div>
      </aside>
      <main><Outlet /></main>
    </div>
  );
}
