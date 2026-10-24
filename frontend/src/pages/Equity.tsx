import { useEffect, useState } from "react";
import type { EquityReport, GroupStat } from "../api/types";
import { MapLegend, RSMap } from "../components/RSMap";
import { NecoComment } from "../components/NecoComment";
import { useQueue } from "../state/QueueContext";

function GroupCard({ title, groups }: { title: string; groups: GroupStat[] }) {
  const max = Math.max(...groups.map((g) => g.avgWait));
  return (
    <div className="card group">
      <h2>{title}</h2>
      {groups.map((g) => (
        <div className="grow" key={g.label}>
          <div className="grow-h"><span>{g.label}</span><b>{g.avgWait} dias</b></div>
          <div className="track"><i style={{ width: `${(g.avgWait / max) * 100}%` }} /></div>
          <small>{g.total} pacientes · {g.overduePct}% passaram do prazo</small>
        </div>
      ))}
    </div>
  );
}

export function Equity() {
  const { backend } = useQueue();
  const [data, setData] = useState<EquityReport | null>(null);
  const [selected, setSelected] = useState<string>();

  useEffect(() => { backend.getEquity().then(setData).catch(console.error); }, [backend]);
  if (!data) return <section className="page"><p className="empty">Carregando…</p></section>;

  const [near, , far] = data.byDistance;
  const gap = far.avgWait - near.avgWait;
  const city = data.cities.find((c) => c.name === selected);
  const ranking = [...data.cities].filter((c) => c.total >= 5).sort((a, b) => b.avgWait - a.avgWait).slice(0, 8);

  return (
    <section className="page wide">
      <div className="head">
        <div><h1>Equidade</h1><p className="sub">Onde estão os pacientes e se alguém espera mais por morar longe, pela idade ou pelo sexo.</p></div>
      </div>

      <NecoComment
        className="insight" reloadKey="equity" load={backend.getEquityInsight}
        fallback={() => ({
          text: gap > 30
            ? `Quem mora a mais de 200 km espera em média ${gap} dias a mais (${far.avgWait} contra ${near.avgWait}), e ${far.overduePct}% já passaram do prazo. A prioridade clínica não usa a distância, então essa diferença vem do acesso e merece atenção da gestão.`
            : "Não encontrei diferença relevante de espera por distância.",
          source: "regras", verified: true,
        })}
      />

      <div className="eq-grid">
        <div className="card map-card">
          <RSMap cities={data.cities} selected={selected} onSelect={(n) => setSelected(n === selected ? undefined : n)} />
          <MapLegend cities={data.cities} />
        </div>
        <div className="card side-card">
          {city ? (
            <>
              <div className="list-h"><h2>{city.name}</h2><button className="link" onClick={() => setSelected(undefined)}>Limpar</button></div>
              <dl className="kv city-kv">
                <dt>Pacientes na fila</dt><dd>{city.total}</dd>
                <dt>Espera média</dt><dd>{city.avgWait} dias</dd>
                <dt>Passaram do prazo</dt><dd>{city.overdue} ({Math.round((city.overdue / city.total) * 100)}%)</dd>
                <dt>Urgentes (A1/A2)</dt><dd>{city.urgent}</dd>
                <dt>Distância média</dt><dd>{city.distanceKm != null ? `${city.distanceKm} km` : "—"}</dd>
              </dl>
            </>
          ) : (
            <>
              <div className="list-h"><h2>Maior espera média</h2></div>
              <ol className="rank">
                {ranking.map((c) => (
                  <li key={c.name}>
                    <button onClick={() => setSelected(c.name)}>
                      <span>{c.name}<small>{c.total} casos · {c.distanceKm ?? "—"} km</small></span><b>{c.avgWait} d</b>
                    </button>
                  </li>
                ))}
              </ol>
              <p className="note" style={{ padding: "0 20px 16px", margin: 0 }}>Municípios com 5 casos ou mais. Clique no mapa para ver um município.</p>
            </>
          )}
        </div>
      </div>

      <div className="groups">
        <GroupCard title="Por distância do hospital" groups={data.byDistance} />
        <GroupCard title="Por faixa etária" groups={data.byAge} />
        <GroupCard title="Por sexo" groups={data.bySex} />
      </div>
    </section>
  );
}
