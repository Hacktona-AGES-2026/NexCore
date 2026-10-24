import { useState } from "react";
import type { AuditEntry, AuditKind } from "../api/types";
import { CheckIcon, DownloadIcon } from "../components/icons";
import { useQueue } from "../state/QueueContext";

const BADGE: Record<AuditKind, string> = { recalc: "Neco", intake: "API", manual: "Manual", validation: "Validação" };
const FILTERS: [string, string, AuditKind[]][] = [
  ["todos", "Todos", ["recalc", "intake", "manual", "validation"]],
  ["neco", "Neco", ["recalc", "intake"]],
  ["man", "Manuais", ["manual"]],
  ["val", "Validações", ["validation"]],
];

function describe(a: AuditEntry) {
  if (a.kind === "validation") return `validou a posição ${a.to}`;
  if (a.from == null) return `incluiu na posição ${a.to}`;
  if (a.from === a.to) return `manteve na posição ${a.to}`;
  return `moveu de ${a.from} para ${a.to}`;
}

function exportCsv(audit: AuditEntry[]) {
  const q = (s: string) => `"${s.replace(/"/g, '""')}"`;
  const lines = ["horario,autor,tipo,solicitacao_id,de,para,justificativa,hash,hash_anterior",
    ...[...audit].reverse().map((a) => [a.at, q(a.author), a.kind, a.entryId, a.from ?? "", a.to, q(a.justification), a.hash, a.prevHash].join(","))];
  const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
  const link = Object.assign(document.createElement("a"), { href: url, download: "auditoria_fila.csv" });
  link.click();
  URL.revokeObjectURL(url);
}

export function Audit() {
  const { audit } = useQueue();
  const [filter, setFilter] = useState("todos");
  const kinds = FILTERS.find((f) => f[0] === filter)![2];
  const list = audit.filter((a) => kinds.includes(a.kind));
  // Verificação no cliente: cada registro aponta para o hash do anterior.
  const chainOk = audit.every((a, i) => i === audit.length - 1 || a.prevHash === audit[i + 1].hash);

  return (
    <section className="page">
      <div className="head">
        <div><h1>Auditoria</h1><p className="sub">Toda mudança na fila, com autor e motivo.</p></div>
        <button className="btn" onClick={() => exportCsv(audit)}><DownloadIcon />Exportar CSV</button>
      </div>
      <div className="bar">
        <div className="seg">{FILTERS.map(([k, l]) => <button key={k} className={filter === k ? "on" : ""} onClick={() => setFilter(k)}>{l}</button>)}</div>
      </div>
      <div className="card">
        <ul className="log">
          {list.length ? list.map((a) => (
            <li key={a.id}>
              <time>{new Date(a.at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}</time>
              <div>
                <div className="t"><span className={`badge ${a.kind}`}>{BADGE[a.kind]}</span>{a.author} <em>{describe(a)} ·</em> {a.entryName}</div>
                <p>{a.justification}</p>
              </div>
              <div className="h" title={`hash ${a.hash} ← ${a.prevHash}`}>#{a.hash}</div>
            </li>
          )) : <li><span /><span className="muted">Nenhum registro.</span></li>}
        </ul>
      </div>
      <div className="chain">
        <CheckIcon />
        <span>{chainOk ? `${audit.length} registros encadeados por hash. Nenhuma alteração detectada.` : "Cadeia quebrada: um registro foi alterado."}</span>
      </div>
    </section>
  );
}
