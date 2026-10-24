import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import type { NecoAnswer } from "../api/types";
import { CLASS_LABEL } from "../domain/queue";
import { useQueue } from "../state/QueueContext";
import { Neco } from "./Neco";

interface Msg { from: "me" | "neco"; text: string; answer?: NecoAnswer }

const STARTERS = [
  "Por que a Gabriela está na posição dela?",
  "Quem da ortopedia passou do prazo?",
  "Quem mora longe espera mais?",
  "Quantas pendências de dados temos?",
];

/** Painel flutuante "Pergunte ao Neco". Abre pelo botão ou com Ctrl+K. */
export function AskNeco() {
  const { backend, entry } = useQueue();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [thinking, setThinking] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setOpen((o) => !o); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  useEffect(() => { if (open) input.current?.focus(); }, [open]);
  useEffect(() => { list.current?.scrollTo({ top: list.current.scrollHeight, behavior: "smooth" }); }, [msgs, thinking]);

  async function ask(q: string) {
    if (!q.trim() || thinking) return;
    setMsgs((m) => [...m, { from: "me", text: q }]);
    setText("");
    setThinking(true);
    try {
      const a = await backend.ask({ question: q });
      setMsgs((m) => [...m, { from: "neco", text: a.text, answer: a }]);
    } catch {
      setMsgs((m) => [...m, { from: "neco", text: "Não consegui consultar a fila agora. Tente de novo em instantes." }]);
    } finally {
      setThinking(false);
    }
  }
  const submit = (e: FormEvent) => { e.preventDefault(); ask(text); };

  return (
    <>
      <button className={`ask-fab ${open ? "hide" : ""}`} onClick={() => setOpen(true)} aria-label="Pergunte ao Neco">
        <Neco size={28} invert /><span>Pergunte ao Neco</span><kbd>Ctrl K</kbd>
      </button>
      <div className={`ask ${open ? "on" : ""}`} role="dialog" aria-label="Pergunte ao Neco">
        <div className="ask-h">
          <Neco size={40} busy={thinking} />
          <div><b>Pergunte ao Neco</b><small>Consulta a fila e explica. Não muda posições.</small></div>
          <button className="x" onClick={() => setOpen(false)} aria-label="Fechar">✕</button>
        </div>
        <div className="ask-b" ref={list}>
          {msgs.length === 0 && (
            <div className="ask-empty">
              <p>Pergunte sobre a fila em português. Por exemplo:</p>
              {STARTERS.map((s) => <button key={s} className="sugg" onClick={() => ask(s)}>{s}</button>)}
            </div>
          )}
          {msgs.map((m, i) => (
            <div key={i} className={`bubble ${m.from}`}>
              <p>{m.text}</p>
              {m.answer?.entryIds?.map((id) => {
                const e = entry(id);
                return e && (
                  <button key={id} className="ref" onClick={() => { navigate(`/fila/${id}`); }}>
                    <b>#{e.position}</b> {e.name}<span className={`cls ${e.urgencyClass}`}><i />{CLASS_LABEL[e.urgencyClass]}</span>
                  </button>
                );
              })}
              {m.answer?.suggestions?.map((s) => <button key={s} className="sugg" onClick={() => ask(s)}>{s}</button>)}
            </div>
          ))}
          {thinking && <div className="bubble neco typing"><i /><i /><i /></div>}
        </div>
        <form className="ask-f" onSubmit={submit}>
          <input ref={input} value={text} onChange={(e) => setText(e.target.value)} placeholder="Escreva sua pergunta" />
          <button className="btn primary" disabled={!text.trim() || thinking}>Enviar</button>
        </form>
      </div>
    </>
  );
}
