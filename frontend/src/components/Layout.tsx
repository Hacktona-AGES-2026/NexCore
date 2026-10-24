import { NavLink, Outlet } from "react-router-dom";
import { useQueue } from "../state/QueueContext";
import { AskNeco } from "./AskNeco";
import { AlertIcon, ChevronDown, HomeIcon, ListIcon, MapIcon, ScreenIcon, ShieldIcon } from "./icons";
import { Neco } from "./Neco";

const STATUS_LABEL = { connecting: "Conectando", open: "Tempo real", closed: "Reconectando" };

export function Layout() {
  const { total, status, pendencies } = useQueue();
  return (
    <div className="app">
      <aside className="side">
        <div className="brand"><Neco size={28} invert /><span>NexCore</span></div>
        <button className="hosp" title="Trocar hospital">Hospital São Lucas <ChevronDown /></button>
        <nav className="nav">
          <NavLink to="/" end><HomeIcon />Início</NavLink>
          <NavLink to="/fila"><ListIcon />Fila<span className="n">{total || ""}</span></NavLink>
          <NavLink to="/pendencias"><AlertIcon />Pendências<span className="n">{pendencies.length || ""}</span></NavLink>
          <NavLink to="/equidade"><MapIcon />Equidade</NavLink>
          <NavLink to="/auditoria"><ShieldIcon />Auditoria</NavLink>
        </nav>
        <a className="screen-link" href="/telao" target="_blank" rel="noreferrer"><ScreenIcon />Abrir telão</a>
        <div className={`conn ${status}`}><i />{STATUS_LABEL[status]}</div>
        <div className="me" style={{ marginTop: 0 }}>
          <div className="av">MA</div>
          <div>Marina Albuquerque<small>Regulação</small></div>
        </div>
      </aside>
      <main><Outlet /></main>
      <AskNeco />
    </div>
  );
}
