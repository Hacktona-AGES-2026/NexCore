// Extração simples por expressões regulares, só para o mock.
// No backend real isso vem do módulo de NLP do Neco.
import type { Highlight, HighlightKind } from "../api/types";

const RULES: [HighlightKind, RegExp][] = [
  ["red_flag", /lesao de tronco[^.,;]*|sincope[^.,;]*|melena[^.,;]*|enterorragia[^.,;]*|queda de Hb[^.,;]*|transfundid\w*[^.,;]*|suboclusao[^.,;]*|subestenosante|crescimento rapido|lesao ulcerada|ulcera de pressao[^.,;]*|acamad\w*[^.,;]*|risco de glaucoma[^.,;]*|dessaturacao[^.,;]*|queda em casa[^.,;]*|perda ponderal[^.,;]*|emagrecimento[^.,;]*|disfagia|sangramento[^.,;]*/gi],
  ["urgency", /\b(?:adeno)?carcinoma(?: \w+)?|\bneoplasia\b|\btumor\b|\bAP confirmad\w*|displasia de alto grau|PET-CT com captacao|angina(?: instavel| CCS \w+)?|BI-RADS ?\w+|DAC triarterial|estadiamento \w+/gi],
  ["events", /internacao(?: recente)?(?: na UPA)?|\bPS\b[^.,;]*|pronto[- ]socorro|\bpiora\b|pede urgencia|reavaliacao da prioridade/gi],
  ["symptoms", /\bdor(?: em repouso| incapacitante| intensa| importante| moderada| aos esforcos| pelvica)?\b|nao sobe escadas|nao consegue[^.,;]*|deambula com dificuldade|uso de muletas|limitacao|parestesias \w+|dependente de familiares|afastado do trabalho/gi],
];

function scan(text: string, field: Highlight["field"]): Highlight[] {
  const found: Highlight[] = [];
  for (const [kind, re] of RULES) {
    for (const m of text.matchAll(re)) {
      const start = m.index!, end = start + m[0].trimEnd().length;
      if (!found.some((h) => start < h.end && end > h.start)) found.push({ field, start, end, kind });
    }
  }
  return found.sort((a, b) => a.start - b.start);
}

export function extractHighlights(clinicalNote: string, regulationNote?: string): Highlight[] {
  return [...scan(clinicalNote, "clinicalNote"), ...(regulationNote ? scan(regulationNote, "regulationNote") : [])];
}
