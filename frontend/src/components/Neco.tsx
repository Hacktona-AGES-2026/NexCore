import { useEffect, useRef } from "react";
import "./sabia/sabia-selo.js";
import type { SabiaSelo } from "./sabia/sabia-selo";

export type NecoMood = "ok" | "think" | "alert";

const SILHUETA =
  "M178 71 L157 66 Q146 55 131 57 Q113 59 97 72 Q78 87 56 106 L14 136 L22 146 " +
  "L62 124 Q82 137 106 134 Q133 130 145 107 Q151 92 152 82 L158 77 Z";
// Abaixo deste tamanho o selo completo perde leitura: usamos o ícone simplificado da referência.
const MIN_ANIMATED = 36;

interface Props {
  size?: number;
  mood?: NecoMood;
  /** Bordô sobre fundo claro (padrão) ou branco sobre fundo bordô. */
  invert?: boolean;
  /** Respira e pisca sozinho. */
  idle?: boolean;
  /** Fica agachado enquanto true; ao voltar para false, levanta e assobia. */
  busy?: boolean;
  /** Cada incremento toca a sequência de análise: agachar → levantar → assobiar. */
  analyze?: number;
  /** Cada incremento faz o Neco assobiar. */
  cheer?: number;
}

/** Neco, o sabiá do NexCore. */
export function Neco({ size = 32, mood = "ok", invert = false, idle = true, busy = false, analyze = 0, cheer = 0 }: Props) {
  const ref = useRef<SabiaSelo>(null);
  const wasBusy = useRef(busy);
  const first = useRef({ analyze, cheer });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (busy) el.agachar();
    else if (wasBusy.current) el.levantar().then((r) => { if (!r.cancelada) el.assobiar(); });
    wasBusy.current = busy;
  }, [busy]);

  useEffect(() => {
    const el = ref.current;
    if (!el || analyze === first.current.analyze) return;
    let alive = true;
    el.agachar();
    const t = setTimeout(() => {
      el.levantar().then((r) => { if (alive && !r.cancelada) el.assobiar(); });
    }, 900);
    return () => { alive = false; clearTimeout(t); };
  }, [analyze]);

  useEffect(() => {
    if (cheer !== first.current.cheer) ref.current?.assobiar();
  }, [cheer]);

  useEffect(() => {
    if (mood === "alert") ref.current?.chacoalhar();
  }, [mood]);

  const color = invert ? "#fff" : "var(--bordo)";
  const bg = invert ? "var(--bordo)" : "var(--sabia-claro)";

  if (size < MIN_ANIMATED) {
    return (
      <svg className="neco" viewBox="0 0 200 200" width={size} height={size} role="img" aria-label="Neco">
        <circle cx="100" cy="100" r="96" fill={color} />
        <g transform="translate(100 102) scale(0.8) translate(-96 -104)">
          <path d={SILHUETA} fill={bg} />
          <circle cx="143" cy="69" r="4.5" fill={color} />
        </g>
      </svg>
    );
  }

  return (
    <sabia-selo
      ref={ref}
      class="neco"
      tamanho={size}
      ocioso={idle ? "" : undefined}
      rotulo="Neco, assistente de priorização"
      style={{ ["--sabia-cor" as string]: color, ["--sabia-fundo" as string]: bg }}
    />
  );
}
