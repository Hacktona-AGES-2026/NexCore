import { useState } from "react";
import { Link } from "react-router-dom";
import type { Pendency, PendencyKind } from "../api/types";
import { Neco } from "../components/Neco";
import { useToast } from "../components/Toast";
import { useQueue } from "../state/QueueContext";

const KINDS: { kind: PendencyKind; label: string; hint: string; actions: [string, string][] }[] = [
  { kind: "cid_flag", label: "Câncer divergente", hint: "A marcação de câncer do cadastro não bate com o CID.", actions: [["fix_cadastro", "Corrigir cadastro"]] },
  { kind: "biopsy", label: "Biópsia × CID", hint: "Biópsia positiva em paciente com CID que não é de câncer.", actions: [["update_cid", "Atualizar CID"], ["keep", "Manter"]] },
  { kind: "duplicate", label: "Duplicatas", hint: "Mesmo paciente com mais de uma solicitação para o mesmo procedimento.", actions: [["merge", "Mesclar"], ["keep_both", "São distintas"]] },
  { kind: "left_queue", label: "Saída da fila", hint: "O call center registrou cirurgia em outro serviço ou desistência.", actions: [["remove", "Confirmar saída"], ["keep", "Manter na fila"]] },
  { kind: "orphan_event", label: "Eventos órfãos", hint: "Eventos que apontam para solicitações fora da fila.", actions: [["archive", "Arquivar"]] },
];

export function Pendencies() {
  const { pendencies, backend, entry } = useQueue();
  const toast = useToast();
  const [kind, setKind] = useState<PendencyKind>("cid_flag");
  const [busy, setBusy] = useState<string | null>(null);
  const current = KINDS.find((k) => k.kind === kind)!;
  const list = pendencies.filter((p) => p.kind === kind);

  async function resolve(p: Pendency, action: string, label: string) {
    setBusy(p.id);
    try {
      await backend.resolvePendency(p.id, { action });
      toast(`${label}: registrado na auditoria.`);
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="page">
      <div className="head">
        <div><h1>Pendências de dados</h1><p className="sub">Inconsistências que o Neco encontrou. Ele já contorna cada uma no cálculo, mas a correção é humana.</p></div>
      </div>
      <div className="bar">
        <div className="seg seg-scroll">
          {KINDS.map((k) => {
            const n = pendencies.filter((p) => p.kind === k.kind).length;
            return <button key={k.kind} className={kind === k.kind ? "on" : ""} onClick={() => setKind(k.kind)}>{k.label} <span className="cnt">{n}</span></button>;
          })}
        </div>
      </div>
      <p className="hint"><Neco size={20} />{current.hint}</p>
      <div className="card">
        {list.length ? list.map((p) => (
          <div className="pend" key={p.id}>
            <div>
              <b>{p.title}</b>
              <p>
                {p.entryIds.filter((id) => entry(id)).length
                  ? p.entryIds.map((id, i) => entry(id) ? <Link key={id} to={`/fila/${id}`}>{i ? ", " : ""}{p.name}</Link> : null)
                  : <span>{p.name}</span>}
                {" · "}<span className="mono">{p.entryIds.join(" · ") || p.id}</span>
              </p>
              <small>{p.detail}</small>
            </div>
            <div className="pend-act">
              {current.actions.map(([action, label], i) => (
                <button key={action} className={`btn ${i === 0 ? "primary" : ""}`} disabled={busy === p.id} onClick={() => resolve(p, action, label)}>{label}</button>
              ))}
            </div>
          </div>
        )) : <p className="empty">Nada pendente aqui.</p>}
      </div>
    </section>
  );
}
