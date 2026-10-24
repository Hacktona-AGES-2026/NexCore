import { useEffect, useRef, useState } from "react";
import type { NecoText } from "../api/types";
import { Neco } from "./Neco";
import { ThinkingDots, useTypewriter } from "./Typing";

// Tempo mínimo "pensando": uma resposta instantânea não faz o Neco piscar.
const MIN_THINKING_MS = 500;

type Phase = "thinking" | "speaking" | "done";

function Speech({ text, boldFirst, onDone }: { text: NecoText; boldFirst: boolean; onDone: () => void }) {
  const segments = [text.text, ...(text.points ?? [])].filter(Boolean);
  const { visible, done } = useTypewriter(segments);
  useEffect(() => { if (done) onDone(); }, [done]); // eslint-disable-line react-hooks/exhaustive-deps
  const caretAt = done ? -1 : Math.max(0, visible.findIndex((v, i) => v.length < segments[i].length));
  return (
    <>
      {visible.map((part, i) => (part || i === 0) && (
        <p key={i}>
          {i === 0 && boldFirst ? <b>{part}</b> : part}
          {caretAt === i && <span className="caret" />}
        </p>
      ))}
    </>
  );
}

/**
 * Um comentário do Neco: ele pensa enquanto a API responde e depois fala,
 * escrevendo letra a letra e cantando. Se a chamada falhar (ou vier vazia),
 * fala o `fallback` do mesmo jeito: para quem lê, é sempre o Neco respondendo.
 * O selo "IA · conferido" só aparece quando o texto veio do modelo.
 */
export function NecoComment({
  load, fallback, reloadKey, className, label, boldFirst = false, thinkingText = "O Neco está pensando…", cheer = 0,
}: {
  load: () => Promise<NecoText>;
  fallback: () => NecoText;
  /** Muda quando o assunto muda (outro paciente, dados novos): o Neco pensa de novo. */
  reloadKey: string;
  className: string;
  label?: string;
  boldFirst?: boolean;
  thinkingText?: string;
  cheer?: number;
}) {
  const [phase, setPhase] = useState<Phase>("thinking");
  const [text, setText] = useState<NecoText | null>(null);
  const latest = useRef({ load, fallback });
  latest.current = { load, fallback };

  useEffect(() => {
    let alive = true;
    setPhase("thinking");
    setText(null);
    const started = Date.now();
    const speak = (t: NecoText) => {
      const wait = Math.max(0, MIN_THINKING_MS - (Date.now() - started));
      setTimeout(() => { if (alive) { setText(t); setPhase("speaking"); } }, wait);
    };
    latest.current.load()
      .then((t) => speak(t.text?.trim() ? t : latest.current.fallback()))
      .catch(() => speak(latest.current.fallback()));
    return () => { alive = false; };
  }, [reloadKey]);

  const badge = text?.source === "ia" && (
    <span className="ai-badge" title="Escrito pelo Neco com IA; todos os números foram conferidos com os dados">IA · conferido</span>
  );

  return (
    <div className={className}>
      <Neco size={44} thinking={phase === "thinking"} singing={phase === "speaking"} cheer={cheer} />
      <div>
        {label && <div className="lbl">{label} {badge}</div>}
        {phase === "thinking" || !text
          ? <p className="thinking-row muted"><ThinkingDots />{thinkingText}</p>
          : <Speech key={reloadKey} text={text} boldFirst={boldFirst} onDone={() => setPhase("done")} />}
        {!label && badge && phase === "done" && <div className="badge-row">{badge}</div>}
      </div>
    </div>
  );
}
