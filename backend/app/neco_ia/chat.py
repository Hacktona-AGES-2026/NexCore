""""Pergunte ao Neco" with the model: it reads the queue only through tools.

The tools are read-only functions over a snapshot taken under the queue's
lock. None of them can move anyone, so "the Neco never changes positions" is a
property of the code, not just a line in the prompt. The SDK turns each
function's signature and docstring into the declaration the model sees, which
is why the docstrings here are Portuguese and written for the model.
"""
import re
import unicodedata

from ..prioritization import CLASS_LABEL, DEADLINE_DAYS
from .texts import BASE_RULES

CHAT_TASK = """Você responde perguntas da administradora da regulação sobre a fila.
- Consulte as ferramentas antes de responder; nunca responda de memória.
- Responda em até 5 frases. Ao citar um paciente, inclua o número da solicitação (ex.: SOL-2025-00274).
- Se a pergunta pedir para mudar uma posição, explique que só a regulação faz isso, pela tela da fila."""
SYSTEM = f"{BASE_RULES}\n\n{CHAT_TASK}"
REQUEST_ID = re.compile(r"SOL-\d{4}-\d{5}")
MAX_ROWS = 15
HISTORY_TURNS = 6


def _norm(text):
    decomposed = unicodedata.normalize("NFD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _row(e):
    return {
        "solicitacao": e["id"], "nome": e["name"], "posicao": e["position"],
        "classe": e["urgencyClass"], "rotulo_classe": CLASS_LABEL[e["urgencyClass"]],
        "procedimento": e["procedure"], "especialidade": e["specialty"], "municipio": e["city"],
        "dias_em_fila": e["daysWaiting"], "prazo_dias": DEADLINE_DAYS[e["urgencyClass"]],
    }


def build_tools(snapshot):
    """`snapshot`: entries (queue order), summary, equity, pendencies, audit, rules."""
    entries = snapshot["entries"]
    by_id = {e["id"]: e for e in entries}

    def buscar_pacientes(texto: str) -> dict:
        """Busca pacientes na fila por nome, número da solicitação ou CID. Devolve até 15 resultados."""
        term = _norm(texto)
        hits = [e for e in entries if term and (term in _norm(e["name"]) or term in _norm(e["id"]) or term in _norm(e["cid"]))]
        return {"total": len(hits), "pacientes": [_row(e) for e in hits[:MAX_ROWS]]}

    def detalhar_solicitacao(solicitacao: str) -> dict:
        """Detalhes de uma solicitação: classe e motivo, fatores do índice, avisos, eventos e vizinhos na fila."""
        e = by_id.get(solicitacao.strip().upper())
        if not e:
            return {"erro": f"Solicitação {solicitacao} não encontrada."}
        index = e["position"] - 1
        return {
            **_row(e),
            "motivo_da_classe": e["classReason"], "indice": e["score"],
            "fatores": {f["key"]: f"{f['value']} de {f['max']}" for f in e["factors"]},
            "avisos": [w["text"] for w in e["warnings"]],
            "posicao_manual": e.get("locked", False),
            "posicao_sem_intervencao_manual": e.get("suggestedPosition"),
            "eventos": [f"{v['date']} {v['type']} {v['result']}: {v['description']}" for v in e["events"][-6:]],
            "logo_acima": _row(entries[index - 1]) if index > 0 else None,
            "logo_abaixo": _row(entries[index + 1]) if index + 1 < len(entries) else None,
        }

    def listar_fila(classe: str = "", especialidade: str = "", municipio: str = "",
                    somente_prazo_vencido: bool = False, limite: int = 10) -> dict:
        """Lista a fila em ordem de prioridade com filtros opcionais (classe A1, A2, B, C ou D; especialidade; município; só quem passou do prazo)."""
        rows = entries
        if classe:
            rows = [e for e in rows if e["urgencyClass"] == classe.strip().upper()]
        if especialidade:
            rows = [e for e in rows if _norm(especialidade) in _norm(e["specialty"])]
        if municipio:
            rows = [e for e in rows if _norm(municipio) in _norm(e["city"])]
        if somente_prazo_vencido:
            rows = [e for e in rows if e["daysWaiting"] > DEADLINE_DAYS[e["urgencyClass"]]]
        return {"total": len(rows), "pacientes": [_row(e) for e in rows[:max(1, min(limite, MAX_ROWS))]]}

    def resumo_fila() -> dict:
        """Totais da fila: por classe (e quantos passaram do prazo), por especialidade, faixas de espera, oncológicos."""
        s = snapshot["summary"]
        return {k: s[k] for k in ("total", "oncologic", "overdueTotal", "byClass", "bySpecialty", "waitBuckets")}

    def equidade() -> dict:
        """Espera média e % fora do prazo por distância do hospital, faixa etária, sexo e município."""
        return snapshot["equity"]

    def pendencias(tipo: str = "") -> dict:
        """Pendências de dados (cid_flag, biopsy, duplicate, left_queue, orphan_event), com contagem por tipo."""
        items = snapshot["pendencies"]
        counts = {}
        for p in items:
            counts[p["kind"]] = counts.get(p["kind"], 0) + 1
        chosen = [p for p in items if not tipo or p["kind"] == tipo]
        return {"por_tipo": counts, "exemplos": [{"titulo": p["title"], "paciente": p["name"]} for p in chosen[:MAX_ROWS]]}

    def historico(solicitacao: str) -> dict:
        """Registros de auditoria de uma solicitação: recálculos, movimentações manuais com justificativa e validações."""
        rid = solicitacao.strip().upper()
        records = [r for r in snapshot["audit"] if r["entryId"] == rid]
        return {"registros": [{k: r[k] for k in ("at", "author", "kind", "from", "to", "justification")} for r in records]}

    def regras_do_neco() -> dict:
        """Como o Neco prioriza: classes, prazos, fatores do índice e a regra de ouro."""
        return snapshot["rules"]

    return [buscar_pacientes, detalhar_solicitacao, listar_fila, resumo_fila, equidade, pendencias, historico, regras_do_neco]


def mentioned_ids(text, entries):
    """Request ids the answer cites, in order, that exist in the queue."""
    known = {e["id"] for e in entries}
    return list(dict.fromkeys(rid for rid in REQUEST_ID.findall(text) if rid in known))


RULES_SUMMARY = {
    "classes": {cls: {"rotulo": CLASS_LABEL[cls], "prazo_dias": DEADLINE_DAYS[cls]} for cls in CLASS_LABEL},
    "ordem": "Primeiro a classe (A1 é a mais urgente), depois o índice de 0 a 97, maior primeiro.",
    "indice": {
        "urgency": "urgência clínica da classe, até 40",
        "wait": "espera em relação ao prazo da classe, até 25",
        "events": "PS, internação, piora e progressão nos últimos 180 dias, até 20",
        "symptoms": "dor e limitação funcional, até 12",
    },
    "regra_de_ouro": "Nenhum paciente com câncer (CID iniciado por C) fica abaixo de alguém sem urgência clínica.",
    "manual": "A regulação pode mover um paciente com justificativa; a posição fica travada e vai para a auditoria.",
}
