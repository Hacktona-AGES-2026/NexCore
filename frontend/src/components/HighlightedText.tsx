import type { Highlight, HighlightKind } from "../api/types";

export const HIGHLIGHT_LABEL: Record<HighlightKind, string> = {
  red_flag: "Sinal de gravidade",
  urgency: "Diagnóstico",
  events: "Evento",
  symptoms: "Dor e função",
};

export function HighlightedText({ text, highlights }: { text: string; highlights: Highlight[] }) {
  const parts: JSX.Element[] = [];
  let cursor = 0;
  highlights.forEach((h, i) => {
    if (h.start > cursor) parts.push(<span key={`t${i}`}>{text.slice(cursor, h.start)}</span>);
    parts.push(<mark key={`h${i}`} className={`hl ${h.kind}`} title={HIGHLIGHT_LABEL[h.kind]}>{text.slice(h.start, h.end)}</mark>);
    cursor = h.end;
  });
  if (cursor < text.length) parts.push(<span key="end">{text.slice(cursor)}</span>);
  return <>{parts}</>;
}

export function HighlightLegend({ highlights }: { highlights: Highlight[] }) {
  const kinds = (Object.keys(HIGHLIGHT_LABEL) as HighlightKind[]).filter((k) => highlights.some((h) => h.kind === k));
  return (
    <div className="legend">
      {kinds.map((k) => <span key={k}><i className={`hl ${k}`} />{HIGHLIGHT_LABEL[k]}</span>)}
    </div>
  );
}
