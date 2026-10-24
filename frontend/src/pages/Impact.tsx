import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/backend";
import type { ImpactReport, VerifierRun } from "../api/types";
import { CheckIcon, DownloadIcon } from "../components/icons";
import { Neco } from "../components/Neco";
import { useToast } from "../components/Toast";
import { officialCsv } from "../domain/officialCsv";
import { CLASS_LABEL } from "../domain/queue";
import { useQueue } from "../state/QueueContext";

const PRIORITIES = ["alta", "media", "baixa", "vazia"] as const;
const PRIORITY_LABEL = { alta: "Alta", media: "Média", baixa: "Baixa", vazia: "Vazia" };

function VerifierCard({ title, run }: { title: string; run: VerifierRun }) {
  return (
    <div className={`card verdict-card ${run.ok ? "pass" : "fail"}`}>
      <div className="vc-h">
        <span className="vc-icon">{run.ok ? <CheckIcon /> : "✕"}</span>
        <div>
          <small>{title}</small>
          <b>{run.ok ? "Aprovada no verificador oficial" : "Reprovada no verificador oficial"}</b>
        </div>
      </div>
      <p>
        {run.violacoes === 0
          ? "Nenhum paciente com câncer abaixo de quem não tem urgência clínica."
          : <><b>{run.violacoes} pacientes com câncer</b> ficam abaixo de alguém sem urgência clínica.</>}
      </p>
      <details>
        <summary>Saída do verificador</summary>
        <pre>{run.output}</pre>
      </details>
    </div>
  );
}

/** Compara um indicador do verificador entre a fila de hoje e a do Neco. */
function Indicator({ label, hint, manual, neco, unit, max, lowerIsBetter = false }: {
  label: string; hint: string; manual: number | null; neco: number | null; unit: string; max: number; lowerIsBetter?: boolean;
}) {
  if (manual == null || neco == null) return null;
  const better = lowerIsBetter ? neco < manual : neco > manual;
  return (
    <div className="ind">
      <div className="ind-h"><b>{label}</b><small>{hint}</small></div>
      <div className="ind-row"><span>Fila de hoje</span><div className="track"><i className="manual" style={{ width: `${(manual / max) * 100}%` }} /></div><em>{manual}{unit}</em></div>
      <div className="ind-row"><span>Neco</span><div className="track"><i style={{ width: `${(neco / max) * 100}%` }} /></div><em className={better ? "better" : ""}>{neco}{unit}</em></div>
    </div>
  );
}

export function Impact() {
  const { backend, entry, entries, total } = useQueue();
  const toast = useToast();
  const [data, setData] = useState<ImpactReport | null>(null);
  const [exporting, setExporting] = useState(false);

  useEffect(() => { backend.getImpact().then(setData).catch(console.error); }, [backend]);

  async function download() {
    setExporting(true);
    try {
      let csv: string;
      try {
        csv = await backend.exportQueueCsv();
      } catch (err) {
        // Backend ainda sem /fila/exportar: monta a partir da fila ao vivo, se ela estiver completa.
        if (!(err instanceof ApiError && err.status === 404) || entries.length !== total) throw err;
        csv = officialCsv(entries);
      }
      const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
      Object.assign(document.createElement("a"), { href: url, download: "fila_priorizada.csv" }).click();
      URL.revokeObjectURL(url);
      toast("fila_priorizada.csv baixado.");
    } catch (err) {
      toast(err instanceof Error ? err.message : "Não foi possível exportar.");
    } finally {
      setExporting(false);
    }
  }

  if (!data) return <section className="page"><p className="empty">Carregando…</p></section>;
  const { neco, manual } = data.verifier;
  const h = data.headline;
  const maxCell = Math.max(...data.matrix.flatMap((r) => PRIORITIES.map((p) => r[p])));
  const mismatch = (cls: string, p: string) => (["A1", "A2"].includes(cls) && ["baixa", "vazia"].includes(p)) || (cls === "D" && p === "alta");

  return (
    <section className="page wide">
      <div className="head">
        <div><h1>Impacto do Neco</h1><p className="sub">A fila do Neco comparada com a fila de hoje, pelo verificador oficial do desafio.</p></div>
        <button className="btn primary" onClick={download} disabled={exporting}><DownloadIcon />{exporting ? "Gerando…" : "Baixar fila_priorizada.csv"}</button>
      </div>

      <div className="insight">
        <Neco size={44} cheer={neco.ok ? 1 : 0} />
        <p>
          Dos <b>{h.a1Total} casos mais graves</b> (câncer com piora recente), a regulação tinha marcado <b>{h.a1Low} como prioridade baixa ou vazia</b>.
          Ao mesmo tempo, <b>{h.dHigh} casos sem urgência</b> ocupavam prioridade alta. Na fila de hoje, {manual.violacoes} pacientes com câncer ficam
          atrás de quem não tem urgência; na do Neco, {neco.violacoes}.
        </p>
      </div>

      <div className="verdicts">
        <VerifierCard title="Fila do Neco" run={neco} />
        <VerifierCard title="Fila de hoje (prioridade manual)" run={manual} />
      </div>

      <div className="impact-grid">
        <div className="card pad">
          <h2>Indicadores do verificador</h2>
          <Indicator label="Pacientes com câncer no primeiro terço" hint="quanto mais, melhor" manual={manual.oncoPrimeiroTerco} neco={neco.oncoPrimeiroTerco} unit="%" max={100} />
          <Indicator label="Posição mediana dos pacientes com câncer" hint="quanto menor, melhor" manual={manual.medianaOnco} neco={neco.medianaOnco} unit="ª" max={data.total} lowerIsBetter />
          <Indicator label="PS ou internação recente na primeira metade" hint="quanto mais, melhor" manual={manual.psPrimeiraMetade} neco={neco.psPrimeiraMetade} unit="%" max={100} />
          <Indicator label="Sem urgência clínica no último terço" hint="quanto mais, melhor" manual={manual.calmosUltimoTerco} neco={neco.calmosUltimoTerco} unit="%" max={100} />
        </div>

        <div className="card pad">
          <h2>Classe do Neco × prioridade manual</h2>
          <p className="muted small">Em destaque, os desencontros: casos graves com prioridade baixa ou vazia, e casos sem urgência com prioridade alta.</p>
          <table className="matrix">
            <thead><tr><th />{PRIORITIES.map((p) => <th key={p}>{PRIORITY_LABEL[p]}</th>)}</tr></thead>
            <tbody>
              {data.matrix.map((r) => (
                <tr key={r.cls}>
                  <th><span className={`cls ${r.cls}`}><i />{r.cls}</span></th>
                  {PRIORITIES.map((p) => (
                    <td key={p} className={mismatch(r.cls, p) && r[p] ? "miss" : ""} style={{ ["--a" as string]: r[p] / maxCell }}>{r[p]}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <div className="list-h"><h2>Quem mais subiu</h2><span className="muted small">posição na fila de hoje → posição no Neco</span></div>
        <ul className="movers">
          {data.movers.map((m) => {
            const name = entry(m.id)?.name ?? m.initials;
            return (
              <li key={m.id}>
                <span className="mv-pos"><s>{m.manualPosition}º</s> → <b>{m.necoPosition}º</b></span>
                <span className="mv-who">
                  {entry(m.id) ? <Link to={`/fila/${m.id}`}>{name}</Link> : <b>{name}</b>}
                  <small>{m.procedure} · {m.reason}</small>
                </span>
                <span className={`cls ${m.cls}`}><i />{CLASS_LABEL[m.cls]}</span>
                <span className="mv-prio">Regulação: {m.manualPriority}</span>
              </li>
            );
          })}
        </ul>
      </div>
      <p className="note">
        {data.baseline} A fila do Neco é a mesma do arquivo exportado.
        {data.source === "referencia" && " Comparação gerada por entrega/gerar_entrega.py com o verificador oficial, enquanto o backend não calcula este painel."}
      </p>
    </section>
  );
}
