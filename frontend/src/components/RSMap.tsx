import type { CityStat } from "../api/types";

// Contorno simplificado do RS (lon, lat), desenhado à mão: serve para
// localizar os municípios, não para medir. Funciona offline no telão.
const OUTLINE: [number, number][] = [
  [-57.64, -30.18], [-57.08, -29.76], [-56.75, -29.35], [-56.3, -28.95], [-56.0, -28.62], [-55.6, -28.2], [-55.13, -27.88],
  [-54.67, -27.55], [-54.25, -27.42], [-53.85, -27.13], [-53.5, -27.2], [-53.2, -27.15], [-52.8, -27.25], [-52.3, -27.38],
  [-51.9, -27.47], [-51.5, -27.65], [-51.2, -27.88], [-50.8, -28.1], [-50.35, -28.35], [-49.95, -28.62], [-49.72, -29.3],
  [-50.0, -29.75], [-50.3, -30.25], [-50.6, -30.75], [-51.0, -31.25], [-51.5, -31.7], [-52.05, -32.1], [-52.4, -32.6],
  [-52.8, -33.1], [-53.37, -33.74], [-53.5, -33.15], [-53.3, -32.85], [-53.2, -32.6], [-53.4, -32.55], [-53.8, -32.2],
  [-54.16, -31.87], [-54.6, -31.55], [-55.1, -31.25], [-55.53, -30.89], [-56.0, -30.62], [-56.45, -30.39], [-57.0, -30.3],
];
const LAGOA_DOS_PATOS: [number, number][] = [
  [-51.25, -30.25], [-51.05, -30.4], [-50.85, -30.75], [-51.05, -31.1], [-51.5, -31.5], [-51.85, -31.85], [-52.08, -32.05],
  [-52.15, -31.85], [-51.85, -31.45], [-51.45, -31.0], [-51.3, -30.6],
];
const LABELED = new Set(["Porto Alegre", "Pelotas", "Santa Maria", "Uruguaiana", "Passo Fundo", "Caxias do Sul", "Bagé", "Santa Rosa", "Torres", "Rio Grande", "Erechim"]);

const LON0 = -57.8, LAT0 = -27.0, K = 100, COS = Math.cos((30.4 * Math.PI) / 180);
const px = (lon: number, lat: number): [number, number] => [(lon - LON0) * COS * K + 10, (LAT0 - lat) * K + 10];
const path = (pts: [number, number][]) => "M" + pts.map(([lo, la]) => px(lo, la).map((v) => v.toFixed(1)).join(",")).join("L") + "Z";

function shade(t: number) {
  const a = [240, 221, 225], b = [92, 18, 34];
  return `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * t)).join(",")})`;
}

export function RSMap({ cities, selected, onSelect, big = false }: {
  cities: CityStat[]; selected?: string; onSelect?: (name: string) => void; big?: boolean;
}) {
  const waits = cities.map((c) => c.avgWait);
  const min = Math.min(...waits), max = Math.max(...waits);
  const maxTotal = Math.max(...cities.map((c) => c.total));
  // Desenha os menores por cima para não sumirem atrás de Porto Alegre.
  const ordered = [...cities].sort((a, b) => b.total - a.total);
  return (
    <svg className={`rsmap ${big ? "big" : ""}`} viewBox="0 0 720 700" role="img" aria-label="Mapa do RS com casos por município">
      <path d={path(OUTLINE)} className="land" />
      <path d={path(LAGOA_DOS_PATOS)} className="water" />
      {ordered.map((c) => {
        const [x, y] = px(c.lon, c.lat);
        const r = 5 + Math.sqrt(c.total / maxTotal) * (big ? 46 : 38);
        const on = selected === c.name;
        return (
          <g key={c.name} className={`city ${on ? "on" : ""}`} onClick={() => onSelect?.(c.name)}>
            <circle cx={x} cy={y} r={r} fill={shade((c.avgWait - min) / (max - min || 1))} />
            <title>{`${c.name}: ${c.total} casos, espera média de ${c.avgWait} dias`}</title>
          </g>
        );
      })}
      {cities.filter((c) => LABELED.has(c.name) || c.name === selected).map((c) => {
        const [x, y] = px(c.lon, c.lat);
        const left = x > 620; // perto da borda direita: rótulo à esquerda do ponto
        return <text key={c.name} x={left ? x - 9 : x + 9} y={y - 9} textAnchor={left ? "end" : "start"} className="lbl">{c.name}</text>;
      })}
    </svg>
  );
}

export function MapLegend({ cities }: { cities: CityStat[] }) {
  const waits = cities.map((c) => c.avgWait);
  return (
    <div className="map-legend">
      <span>Espera média</span>
      <span>{Math.min(...waits)} d</span>
      <i style={{ background: `linear-gradient(90deg, ${shade(0)}, ${shade(1)})` }} />
      <span>{Math.max(...waits)} d</span>
      <span className="muted">· tamanho = casos</span>
    </div>
  );
}
