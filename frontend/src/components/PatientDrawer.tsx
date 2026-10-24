import { useEffect, useState } from "react";
import type { NecoText, QueueEntry } from "../api/types";
import { CLASS_LABEL, CLASS_RANK, DEADLINE_DAYS, FACTOR_LABEL, byPosition, firstName } from "../domain/queue";
import { useQueue } from "../state/QueueContext";
import { HighlightLegend, HighlightedText } from "./HighlightedText";
import { InfoIcon } from "./icons";
import { NecoComment } from "./NecoComment";
import { ReorderModal } from "./ReorderModal";
import { useToast } from "./Toast";

const EVENT_LABEL: Record<string, string> = {
  biopsia: "Biópsia", hba1c: "HbA1c", pronto_socorro: "Pronto-socorro", internacao: "Internação", exame_imagem: "Exame de imagem",
  consulta_reavaliacao: "Reavaliação", contato_telefonico: "Contato telefônico", falta: "Falta",
};
const RESULT_LABEL: Record<string, string> = {
  positivo: "positiva", negativo: "negativa", inconclusivo: "inconclusiva", atendido_liberado: "liberado", observacao: "em observação",
  alta: "alta", estavel: "estável", progressao: "progressão", piora: "piora", melhora: "melhora", atendeu: "atendeu",
  nao_atendeu: "não atendeu", relata_piora: "relata piora", relata_melhora: "relata melhora",
  informou_cirurgia_outro_servico: "operou em outro serviço", desistiu: "desistiu", consulta: "consulta", exame: "exame",
  avaliacao_pre_anestesica: "pré-anestésica",
};
const isHot = (r: string, t: string) => ["positivo", "progressao", "piora", "relata_piora", "observacao"].includes(r) || t === "internacao";
const fmtDate = (d?: string) => (d ? d.split("-").reverse().join("/") : "—");
const fmtNum = (n: number) => String(n).replace(".", ",");

/** A explicação por regras, montada no front: é o que o Neco fala se a API falhar. */
function localExplanation(entry: QueueEntry, above?: QueueEntry): NecoText {
  const deadline = DEADLINE_DAYS[entry.urgencyClass];
  const late = entry.daysWaiting - deadline;
  const points = [
    late > 0
      ? `Espera há ${entry.daysWaiting} dias, ${late} além do prazo de ${deadline} dias.`
      : `Espera há ${entry.daysWaiting} dias, dentro do prazo de ${deadline} dias.`,
  ];
  if (entry.locked && entry.suggestedPosition && entry.suggestedPosition !== entry.position) {
    points.push(`Posição definida manualmente pela regulação; pelos dados, o Neco a colocaria na ${entry.suggestedPosition}ª.`);
  }
  if (above) {
    const why = CLASS_RANK[above.urgencyClass] > CLASS_RANK[entry.urgencyClass] ? "que é mais urgente"
      : above.locked ? "posicionado manualmente" : "que tem índice maior";
    points.push(`Abaixo de #${above.position} ${firstName(above.name)}, ${why}.`);
  }
  return {
    text: `${CLASS_LABEL[entry.urgencyClass]} (${entry.urgencyClass}): ${entry.classReason}.`,
    points: points.slice(0, 3), source: "regras", verified: true,
  };
}

export function PatientDrawer({ entryId, onClose }: { entryId: string | null; onClose: () => void }) {
  const { entry, entries, audit, backend } = useQueue();
  const toast = useToast();
  const [reordering, setReordering] = useState(false);
  const e = entryId ? entry(entryId) : undefined;

  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => ev.key === "Escape" && !reordering && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, reordering]);

  const sorted = [...entries].sort(byPosition);
  const above = e ? sorted[sorted.indexOf(e) - 1] : undefined;
  const validation = e && audit.find((a) => a.entryId === e.id && a.kind === "validation");
  // O Neco pensa de novo quando algo do paciente muda: posição, trava ou auditoria.
  const explanationKey = e ? `${e.id}:${e.position}:${e.locked}:${audit.filter((a) => a.entryId === e.id).length}` : "";

  async function validate() {
    if (!e) return;
    await backend.validate(e.id);
    toast("Validação registrada.");
  }

  return (
    <>
      <div className={`scrim ${e ? "on" : ""}`} onClick={onClose} />
      <aside className={`drawer ${e ? "on" : ""}`} aria-label="Detalhe do paciente">
        {e && (
          <>
            <div className="dr-h">
              <div className="posbox">{e.position}</div>
              <div><h2>{e.name}</h2><p>{e.procedure} · {e.age} anos</p></div>
              <button className="x" onClick={onClose} aria-label="Fechar">✕</button>
            </div>
            <div className="dr-b">
              <NecoComment
                className="why" label="Por que está aqui" boldFirst reloadKey={explanationKey} cheer={validation ? 1 : 0}
                load={() => backend.getExplanation(e.id)} fallback={() => localExplanation(e, above)}
              />
              {e.warnings.map((w) => (
                <div key={w.text} className={`warn ${w.level === "critical" ? "red" : ""}`}><InfoIcon />{w.text}</div>
              ))}
              {validation && <div className="ok">✓ Validado por {validation.author} às {new Date(validation.at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}</div>}

              <div className="sect">O que o Neco leu no texto</div>
              <HighlightLegend highlights={e.highlights} />
              <div className="note-src">
                <span>Médico solicitante</span>
                <p><HighlightedText text={e.clinicalNote} highlights={e.highlights.filter((h) => h.field === "clinicalNote")} /></p>
              </div>
              {e.regulationNote && (
                <div className="note-src">
                  <span>Observações da regulação</span>
                  <p><HighlightedText text={e.regulationNote} highlights={e.highlights.filter((h) => h.field === "regulationNote")} /></p>
                </div>
              )}

              <div className="sect">Como o índice foi composto</div>
              {e.factors.map((f) => (
                <div className="factor" key={f.key}>
                  <b>{FACTOR_LABEL[f.key]}</b><span>{fmtNum(f.value)} de {f.max}</span>
                  <div className="track"><i style={{ width: `${(f.value / f.max) * 100}%` }} /></div>
                </div>
              ))}

              <details>
                <summary>Dados clínicos</summary>
                <dl className="kv">
                  <dt>Solicitação</dt><dd className="mono">{e.id}</dd>
                  <dt>CID</dt><dd>{e.cid} · {e.cidDescription}</dd>
                  <dt>Dor / limitação</dt><dd>{e.pain ?? "—"}/10 · {e.limitation ?? "—"}</dd>
                  <dt>ASA</dt><dd>{e.asa ?? "—"}</dd>
                  <dt>Comorbidades</dt><dd>{e.comorbidities ?? "—"}</dd>
                  <dt>Entrada na fila</dt><dd>{fmtDate(e.enteredAt)}</dd>
                  <dt>Prioridade manual</dt><dd style={{ textTransform: "capitalize" }}>{e.manualPriority ?? "vazia"}</dd>
                </dl>
              </details>
              <details>
                <summary>Eventos ({e.events.length})</summary>
                {e.events.length ? (
                  <ul className="ev">
                    {[...e.events].reverse().map((ev, i) => (
                      <li key={i} className={isHot(ev.result, ev.type) ? "hot" : ""}>
                        <time>{fmtDate(ev.date)}</time>
                        <div>
                          <b>{EVENT_LABEL[ev.type] ?? ev.type} {RESULT_LABEL[ev.result] ?? ""}{ev.value ? ` · ${ev.type === "hba1c" ? ev.value + "%" : ev.value + " dias"}` : ""}</b>
                          <small>{ev.description}</small>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : <p className="muted" style={{ margin: "0 0 16px" }}>Sem eventos.</p>}
              </details>
            </div>
            <div className="dr-f">
              <button className="btn" onClick={() => setReordering(true)}>Mudar posição</button>
              <button className="btn primary" onClick={validate} disabled={!!validation}>Concordo</button>
            </div>
          </>
        )}
      </aside>
      {e && reordering && <ReorderModal entry={e} onClose={() => setReordering(false)} />}
    </>
  );
}
