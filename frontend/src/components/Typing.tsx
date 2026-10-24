import { useEffect, useRef, useState } from "react";

/** Três pontinhos pulando em sequência: o Neco está pensando. */
export function ThinkingDots({ label = "Neco está pensando" }: { label?: string }) {
  return <span className="dots" role="status" aria-label={label}><i /><i /><i /></span>;
}

const reducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/**
 * Revela `segments` letra a letra, um depois do outro (título, depois cada ponto).
 * Devolve o pedaço visível de cada segmento e se terminou. Com `enabled` falso
 * ou movimento reduzido, mostra tudo de uma vez.
 */
export function useTypewriter(segments: string[], { enabled = true, charsPerSecond = 70 } = {}) {
  const total = segments.reduce((n, s) => n + s.length, 0);
  const key = segments.join("\u0000");
  const instant = !enabled || reducedMotion();
  const [count, setCount] = useState(instant ? total : 0);
  const started = useRef(Date.now());

  useEffect(() => {
    if (instant) { setCount(total); return; }
    setCount(0);
    started.current = Date.now();
    const timer = setInterval(() => {
      const next = Math.min(total, Math.floor(((Date.now() - started.current) / 1000) * charsPerSecond));
      setCount(next);
      if (next >= total) clearInterval(timer);
    }, 30);
    return () => clearInterval(timer);
  }, [key, instant]); // eslint-disable-line react-hooks/exhaustive-deps

  let left = count;
  const visible = segments.map((s) => {
    const part = s.slice(0, Math.max(0, left));
    left -= s.length;
    return part;
  });
  return { visible, done: count >= total, count };
}

