import { useEffect, useRef, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import type { NecoAnswer } from "../api/types";
import { CLASS_LABEL } from "../domain/queue";
import { useQueue } from "../state/QueueContext";
import { Neco } from "./Neco";
import { ThinkingDots, useTypewriter } from "./Typing";

interface Msg { id: number; from: "me" | "neco"; text: string; answer?: NecoAnswer }

/** Resposta do Neco escrita letra a letra; os links e sugestões aparecem quando termina. */
function NecoBubble({ msg, animate, onTyping, onDone, children }: {
  msg: Msg; animate: boolean; onTyping: () => void; onDone: () => void; children: React.ReactNode;
}) {
  const { visible, done, count } = useTypewriter([msg.text], { enabled: animate });
  useEffect(() => { if (animate) onTyping(); }, [count]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (done && animate) onDone(); }, [done]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="bubble neco">
      <p>{visible[0]}{!done && <span className="caret" />}</p>
      {done && children}
    </div>
  );
}

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
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [thinking, setThinking] = useState(false);
  // Resposta que está sendo escrita agora (o Neco canta enquanto isso).
  const [typingId, setTypingId] = useState<number | null>(null);
  const nextId = useRef(1);
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
  // Trocar de página ou abrir um paciente fecha o chat, para ele não ficar por cima. A conversa é mantida.
  useEffect(() => { setOpen(false); }, [pathname]);
  // Sem retorno: em navegadores novos scrollTo devolve uma Promise, e o useEffect a trataria como limpeza.
  const scrollDown = () => { list.current?.scrollTo({ top: list.current.scrollHeight }); };
  useEffect(() => { scrollDown(); }, [msgs, thinking]);

  async function ask(q: string) {
    if (!q.trim() || thinking || typingId !== null) return;
    setMsgs((m) => [...m, { id: nextId.current++, from: "me", text: q }]);
    setText("");
    setThinking(true);
    try {
      const history = msgs.slice(-6).map(({ from, text }) => ({ from, text }));
      const a = await backend.ask({ question: q, history });
      const id = nextId.current++;
      setTypingId(id);
      setMsgs((m) => [...m, { id, from: "neco", text: a.text, answer: a }]);
    } catch {
      const id = nextId.current++;
      setTypingId(id);
      setMsgs((m) => [...m, { id, from: "neco", text: "Não consegui consultar a fila agora. Tente de novo em instantes." }]);
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
          <Neco size={40} thinking={thinking} singing={typingId !== null} />
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
          {msgs.map((m) => m.from === "me" ? (
            <div key={m.id} className="bubble me"><p>{m.text}</p></div>
          ) : (
            <NecoBubble key={m.id} msg={m} animate={m.id === typingId} onTyping={scrollDown} onDone={() => setTypingId(null)}>
              {m.answer?.entryIds?.map((id) => {
                const e = entry(id);
                return e && (
                  <button key={id} className="ref" onClick={() => { navigate(`/fila/${id}`); }}>
                    <b>#{e.position}</b> {e.name}<span className={`cls ${e.urgencyClass}`}><i />{CLASS_LABEL[e.urgencyClass]}</span>
                  </button>
                );
              })}
              {m.answer?.suggestions?.map((s) => <button key={s} className="sugg" onClick={() => ask(s)}>{s}</button>)}
            </NecoBubble>
          ))}
          {thinking && <div className="bubble neco waiting"><Neco size={36} thinking /><ThinkingDots /></div>}
        </div>
        <form className="ask-f" onSubmit={submit}>
          <input ref={input} value={text} onChange={(e) => setText(e.target.value)} placeholder="Escreva sua pergunta" />
          <button className="btn primary" disabled={!text.trim() || thinking || typingId !== null}>Enviar</button>
        </form>
      </div>
    </>
  );
}
