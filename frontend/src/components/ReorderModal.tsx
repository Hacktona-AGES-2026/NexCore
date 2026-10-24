import { useState } from "react";
import type { QueueEntry } from "../api/types";
import { goldenRuleViolation, relocate } from "../domain/queue";
import { useQueue } from "../state/QueueContext";
import { Neco } from "./Neco";
import { useToast } from "./Toast";

const REASONS = [
  "Informação clínica nova",
  "Critério clínico não considerado",
  "Erro no dado de origem",
  "Determinação judicial ou do gestor",
];
const MIN_TEXT = 40;

export function ReorderModal({ entry, onClose }: { entry: QueueEntry; onClose: () => void }) {
  const { entries, total, backend } = useQueue();
  const toast = useToast();
  const [pos, setPos] = useState("");
  const [reason, setReason] = useState("");
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const to = Math.max(1, Math.min(total, parseInt(pos) || entry.position));
  const hasPos = !!parseInt(pos) && to !== entry.position;
  // Checagem local só para feedback imediato; o servidor valida de novo.
  const violation = hasPos ? goldenRuleViolation(relocate(entries, entry.id, to)) : null;
  const canSubmit = hasPos && !violation && !!reason && text.trim().length >= MIN_TEXT && !saving;

  async function submit() {
    setSaving(true);
    setError("");
    try {
      await backend.reorder(entry.id, { position: to, reason, justification: text.trim() });
      toast(`Movido de ${entry.position} para ${to}.`);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível salvar.");
      setSaving(false);
    }
  }

  return (
    <div className="modal" onClick={(ev) => ev.target === ev.currentTarget && onClose()}>
      <div className="mbox" role="dialog" aria-modal="true" aria-labelledby="reorder-title">
        <div className="hd">
          <h2 id="reorder-title" style={{ fontSize: 17 }}>Mudar posição</h2>
          <p className="sub" style={{ fontSize: 13 }}>{entry.name} está na posição {entry.position}.</p>
        </div>
        <div className="bd">
          <div className="field">
            <label htmlFor="m-pos">Nova posição</label>
            <input id="m-pos" type="number" min={1} max={total} value={pos} onChange={(e) => setPos(e.target.value)} autoFocus />
          </div>
          <div className="field">
            <label htmlFor="m-cat">Motivo</label>
            <select id="m-cat" value={reason} onChange={(e) => setReason(e.target.value)}>
              <option value="">Selecione</option>
              {REASONS.map((r) => <option key={r}>{r}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="m-txt">Justificativa</label>
            <textarea id="m-txt" value={text} onChange={(e) => setText(e.target.value)} placeholder="O que você verificou e por que a posição deve mudar" />
            <small>{text.trim().length} / {MIN_TEXT}</small>
          </div>
          <div className={`prev ${violation ? "bad" : ""}`}>
            <Neco size={40} mood={violation ? "alert" : "ok"} />
            <span>
              {violation
                ? `Não é possível: ${violation.oncologic.name} tem câncer e ficaria atrás de quem não tem urgência.`
                : hasPos
                  ? `${to < entry.position ? "Sobe" : "Desce"} de ${entry.position} para ${to}. A posição fica travada e o registro vai para a auditoria.`
                  : "Informe a nova posição."}
            </span>
          </div>
          {error && <p className="error">{error}</p>}
        </div>
        <div className="dr-f">
          <button className="btn" onClick={onClose}>Cancelar</button>
          <button className="btn primary" onClick={submit} disabled={!canSubmit}>Confirmar</button>
        </div>
      </div>
    </div>
  );
}
