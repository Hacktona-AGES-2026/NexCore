import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { Pendency, PendencyAction, PendencyPreview } from "../api/types";
import { useQueue } from "../state/QueueContext";
import { Neco } from "./Neco";
import { useToast } from "./Toast";
import { ThinkingDots } from "./Typing";

export const RISK_LABEL = { alto: "Risco alto", medio: "Risco médio", baixo: "Risco baixo" } as const;
const MIN_NOTE = 10;
const fmtDate = (d?: string) => (d ? d.split("-").reverse().join("/") : "");

function initialValues(action: PendencyAction | undefined) {
  return Object.fromEntries((action?.fields ?? []).map((f) => [f.name, f.suggested ?? ""]));
}

/**
 * Painel de correção único para qualquer pendência: mostra as divergências,
 * a evidência e a sugestão do Neco; a ação escolhida pede só os campos dela,
 * e a prévia diz o que muda na fila antes de confirmar.
 */
export function PendencyPanel({ pendency, onClose }: { pendency: Pendency | null; onClose: () => void }) {
  const { backend, entry } = useQueue();
  const toast = useToast();
  const p = pendency;
  const suggested = p?.actions.find((a) => a.id === p.suggestion.actionId);
  const [actionId, setActionId] = useState<string | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  const [preview, setPreview] = useState<PendencyPreview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  // Abre já com a ação sugerida pelo Neco selecionada.
  useEffect(() => {
    setActionId(suggested?.id ?? null);
    setValues(initialValues(suggested));
    setNote("");
    setError("");
  }, [p?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => { if (ev.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const action = p?.actions.find((a) => a.id === actionId);
  const fieldsOk = useMemo(() => !!action && action.fields.every((f) => {
    const v = (values[f.name] ?? "").trim();
    return (!f.required || v) && (!v || !f.pattern || new RegExp(f.pattern).test(v));
  }), [action, values]);
  const noteOk = !action?.requiresJustification || note.trim().length >= MIN_NOTE;

  // Prévia automática quando a ação e os campos estão completos.
  useEffect(() => {
    setPreview(null);
    if (!p || !action || !fieldsOk) return;
    let alive = true;
    setPreviewing(true);
    const timer = setTimeout(() => {
      backend.simulatePendency(p.id, { action: action.id, values })
        .then((r) => { if (alive) setPreview(r); })
        .catch((e) => { if (alive) setPreview({ action: action.id, changes: [], summary: e instanceof Error ? e.message : "Não foi possível simular." }); })
        .finally(() => { if (alive) setPreviewing(false); });
    }, 300);
    return () => { alive = false; clearTimeout(timer); };
  }, [p?.id, action?.id, fieldsOk, JSON.stringify(values)]); // eslint-disable-line react-hooks/exhaustive-deps

  function choose(a: PendencyAction) {
    setActionId(a.id);
    setValues(initialValues(a));
    setError("");
  }

  async function confirm() {
    if (!p || !action) return;
    setSaving(true);
    setError("");
    try {
      await backend.resolvePendency(p.id, { action: action.id, values, note: note.trim() || undefined });
      toast(`${action.label}: corrigido e registrado na auditoria.`);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível salvar.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className={`scrim ${p ? "on" : ""}`} onClick={onClose} />
      <aside className={`drawer ${p ? "on" : ""}`} aria-label="Correção da pendência">
        {p && (
          <>
            <div className="dr-h">
              <div className={`risk-box ${p.risk}`}>{p.risk === "alto" ? "!" : p.risk === "medio" ? "•" : "·"}</div>
              <div>
                <p className="kind-line">{p.kindLabel} · <span className={`risk-text ${p.risk}`}>{RISK_LABEL[p.risk]}</span></p>
                <h2>{p.title}</h2>
                <p>
                  {p.entryIds.length
                    ? p.entryIds.map((id, i) => (
                      <span key={id}>{i > 0 && ", "}{entry(id) ? <Link to={`/fila/${id}`}>{entry(id)!.name} (#{entry(id)!.position})</Link> : id}</span>
                    ))
                    : p.name}
                </p>
              </div>
              <button className="x" onClick={onClose} aria-label="Fechar">✕</button>
            </div>
            <div className="dr-b">
              <div className="why">
                <Neco size={44} />
                <div>
                  <div className="lbl">Sugestão do Neco</div>
                  <p>{suggested ? <><b>{suggested.label}.</b> </> : null}{p.suggestion.reason}</p>
                  <p className="muted small">{p.riskReason}</p>
                </div>
              </div>

              <div className="sect">Divergências</div>
              {p.divergences.map((d) => (
                <div className="divergence" key={d.field}>
                  <b>{d.label}</b>
                  <dl>
                    {d.values.map((v) => <div key={v.source}><dt>{v.source}</dt><dd>{v.value}</dd></div>)}
                  </dl>
                </div>
              ))}

              {p.evidence.length > 0 && (
                <>
                  <div className="sect">Evidências</div>
                  {p.evidence.map((ev, i) => (
                    <div className="note-src" key={i}>
                      <span>{ev.label}{ev.date && ` · ${fmtDate(ev.date)}`}</span>
                      <p>{ev.text}</p>
                    </div>
                  ))}
                </>
              )}

              <div className="sect">O que fazer</div>
              <div className="actions-pick">
                {p.actions.map((a) => (
                  <button key={a.id} className={`pick ${actionId === a.id ? "on" : ""} ${a.danger ? "danger" : ""}`} onClick={() => choose(a)}>
                    <b>{a.label}{a.id === suggested?.id && <span className="sugg-tag">sugerida</span>}</b>
                    <small>{a.description}</small>
                  </button>
                ))}
              </div>

              {action && (
                <div className="action-form">
                  {action.fields.map((f) => (
                    <div className="field" key={f.name}>
                      <label htmlFor={`pf-${f.name}`}>{f.label}{f.required && " *"}</label>
                      {f.type === "select" ? (
                        <select id={`pf-${f.name}`} value={values[f.name] ?? ""} onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}>
                          <option value="">Selecione</option>
                          {f.options?.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                        </select>
                      ) : (
                        <input id={`pf-${f.name}`} value={values[f.name] ?? ""} onChange={(e) => setValues({ ...values, [f.name]: e.target.value })} />
                      )}
                      {f.help && <small className="help">{f.help}</small>}
                    </div>
                  ))}
                  <div className="field">
                    <label htmlFor="pf-note">Justificativa{action.requiresJustification ? " *" : " (opcional)"}</label>
                    <textarea id="pf-note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="O que você conferiu para decidir" />
                    {action.requiresJustification && <small>{note.trim().length} / {MIN_NOTE}</small>}
                  </div>
                  <div className={`prev ${action.danger ? "warn-prev" : ""}`}>
                    <Neco size={24} />
                    <span>
                      {!fieldsOk ? "Preencha os campos para ver o efeito na fila."
                        : previewing || !preview ? <span className="thinking-row"><ThinkingDots />Calculando o efeito…</span>
                        : preview.summary}
                    </span>
                  </div>
                  {error && <p className="error">{error}</p>}
                </div>
              )}
            </div>
            <div className="dr-f">
              <button className="btn" onClick={onClose}>Cancelar</button>
              <button className={`btn primary ${action?.danger ? "danger-btn" : ""}`} disabled={!action || !fieldsOk || !noteOk || saving} onClick={confirm}>
                {saving ? "Salvando…" : action ? `Confirmar: ${action.label}` : "Escolha uma ação"}
              </button>
            </div>
          </>
        )}
      </aside>
    </>
  );
}
