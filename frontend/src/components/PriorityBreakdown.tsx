import type { QueueEntry, ScoreFactor } from "../api/types";
import { FACTOR_LABEL, isDpss } from "../domain/queue";

const br = (n: number, digits = 2) => n.toLocaleString("pt-BR", { maximumFractionDigits: digits });

function FactorRow({ f, dpss }: { f: ScoreFactor; dpss: boolean }) {
  const share = f.max > 0 ? f.value / f.max : 0;
  // No DPSS a espera é T/M: passa de 1 quando o prazo venceu, e a barra fica cheia.
  const shown = dpss && f.key === "wait" ? `${br(f.value)}× o prazo`
    : dpss && f.key === "clinical" ? `${br(f.value * 100, 0)}%`
    : `${br(f.value)} de ${br(f.max)}`;
  return (
    <div className="factor">
      <b>{FACTOR_LABEL[f.key] ?? f.key}</b><span>{shown}</span>
      <div className={`track ${share > 1 ? "over" : ""}`}><i style={{ width: `${Math.min(share, 1) * 100}%` }} /></div>
      {dpss && f.key === "wait" && share > 1 && <small className="factor-note">Prazo da classe vencido: conta como {br(f.value)} vezes o prazo.</small>}
    </div>
  );
}

/**
 * "Como o índice foi composto". Mostra os fatores que o backend mandar; no
 * modelo DPSS mostra também a conta inteira: índice = espera × (1 + clínico + social).
 */
export function PriorityBreakdown({ entry }: { entry: QueueEntry }) {
  const dpss = isDpss(entry);
  const f = Object.fromEntries(entry.factors.map((x) => [x.key, x.value]));
  const p = entry.priority;
  return (
    <>
      <div className="sect">Como o índice foi composto</div>
      {dpss && p && (
        <div className="formula">
          {entry.score == null
            ? <p>Sem índice: o DPS não conseguiu inferir a classe SWALIS com segurança, então o caso fica no fim da sua faixa.</p>
            : <p>
                <b>Índice {br(entry.score)}</b> = espera {br(f.wait)} × (1 + clínico {br(f.clinical)} + social {br(f.social)})
              </p>}
          <small>
            {p.protected ? "Faixa protegida (A1/A2 ou câncer): fica acima de quem não tem urgência. " : ""}
            {p.socioeconomicVulnerability != null
              ? `Vulnerabilidade social do município ${br(p.socioeconomicVulnerability, 3)}, com peso ${br(p.socioeconomicWeight)}.`
              : "Sem dado socioeconômico do município."}
          </small>
        </div>
      )}
      {entry.factors.map((x) => <FactorRow key={x.key} f={x} dpss={dpss} />)}
    </>
  );
}
