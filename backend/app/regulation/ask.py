""""Pergunte ao Neco" by keyword — a stand-in until the LLM version (P3).

A port of the front's mock (`frontend/src/mock/neco.ts`): same intents, same
answers, now over the server's real queue. It only reads; it never moves anyone.
When the LLM with tools lands, it replaces `answer` and keeps the reply shape
`{text, entryIds?, suggestions?}`.
"""
import re
import unicodedata

from ..prioritization import CLASS_LABEL, DEADLINE_DAYS

SUGGESTIONS = [
    "Por que a Gabriela está na posição dela?",
    "Quem da ortopedia passou do prazo?",
    "Quantos casos A1 temos?",
    "Quem mora longe espera mais?",
]
NOT_UNDERSTOOD = (
    "Não entendi essa pergunta. Posso explicar a posição de um paciente, comparar dois "
    "pacientes, contar casos por classe, listar quem passou do prazo ou falar de equidade "
    "e pendências."
)


def _norm(text):
    decomposed = unicodedata.normalize("NFD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _late(e):
    return e["daysWaiting"] - DEADLINE_DAYS[e["urgencyClass"]]


def _more_urgent(a, b):
    """True when `a` is in the safety band (A1/A2 or cancer) and `b` is not."""
    return a["priority"]["protected"] and not b["priority"]["protected"]


def find_patients(question, entries):
    """Full name wins; otherwise match the first name as a whole word."""
    text = _norm(question)
    full = [e for e in entries if _norm(e["name"]) and _norm(e["name"]) in text]
    if full:
        return full
    words = set(re.split(r"[^a-z]+", text))
    return [e for e in entries if _norm(e["name"].split(" ")[0]) in words]


def explain(e, entries):
    index = entries.index(e)
    above = entries[index - 1] if index > 0 else None
    late = _late(e)
    cls = e["urgencyClass"]
    text = f"{e['name']} está na posição {e['position']} como {CLASS_LABEL[cls]} ({cls}): {e['classReason']}. "
    text += (
        f"Espera há {e['daysWaiting']} dias, {late} além do prazo de {DEADLINE_DAYS[cls]}. "
        if late > 0 else f"Espera há {e['daysWaiting']} dias, dentro do prazo. "
    )
    if above:
        text += (
            f"Logo acima está {above['name']}, que está na faixa protegida (A1/A2 ou câncer)."
            if _more_urgent(above, e)
            else f"Logo acima está {above['name']}, com DPSS {above['score']} contra {e['score']}."
        )
    if e["warnings"]:
        text += f" Atenção: {e['warnings'][0]['text']}"
    return text


def answer(question, entries, summary, equity, pendencies):
    """`entries` in queue order, as the front receives them."""
    q = _norm(question)
    people = find_patients(question, entries)

    if len(people) >= 2 and re.search(r"acima|abaixo|frente|antes|depois|compar", q):
        a, b = sorted(people, key=lambda e: e["position"])[:2]
        if _more_urgent(a, b):
            why = (
                f"{a['name']} é {CLASS_LABEL[a['urgencyClass']]} ({a['classReason']}), enquanto "
                f"{b['name']} é {CLASS_LABEL[b['urgencyClass']]} ({b['classReason']}). "
                "A faixa protegida (A1/A2 e câncer) vem antes do DPSS."
            )
        else:
            factor = (
                "espera em relação ao prazo" if a["factors"][0]["value"] > b["factors"][0]["value"]
                else "fator clínico ou vulnerabilidade social"
            )
            why = (
                f"{a['name']} tem DPSS {a['score']} e {b['name']} {b['score']}; "
                f"a diferença vem principalmente de {factor}."
            )
        return {
            "text": f"{a['name']} está na posição {a['position']} e {b['name']} na {b['position']}. {why}",
            "entryIds": [a["id"], b["id"]],
        }
    if people:
        return {"text": explain(people[0], entries), "entryIds": [people[0]["id"]]}

    cls = re.search(r"\b(a1|a2|b|c|d)\b", q)
    if "quant" in q and cls:
        row = next(c for c in summary["byClass"] if c["cls"].lower() == cls.group(1))
        return {
            "text": (
                f"Temos {row['total']} casos {row['cls']} ({CLASS_LABEL[row['cls']]}). Deles, "
                f"{row['overdue']} já passaram do prazo de {DEADLINE_DAYS[row['cls']]} dias."
            ),
        }
    if re.search(r"longe|distanc|interior|equidade|desigual|municip", q):
        near, _, far = equity["byDistance"]
        return {
            "text": (
                f"Sim. Quem mora a mais de 200 km espera em média {far['avgWait']} dias, contra "
                f"{near['avgWait']} de quem mora até 50 km. {far['overduePct']}% dos pacientes "
                f"distantes já passaram do prazo, contra {near['overduePct']}% dos próximos. "
                "Vale olhar o painel de equidade."
            ),
            "suggestions": ["Quantos casos A1 temos?"],
        }
    if re.search(r"pendenc|dado|duplic|inconsist|cadastro", q):
        def count(kind):
            return sum(1 for p in pendencies if p["kind"] == kind)
        return {
            "text": (
                f"Há {len(pendencies)} pendências de dados: {count('cid_flag')} cadastros com câncer "
                f"divergente do CID, {count('duplicate')} possíveis duplicatas, {count('biopsy')} "
                f"biópsias positivas com CID benigno, {count('left_queue')} pacientes que podem ter "
                f"saído da fila e {count('orphan_event')} eventos sem solicitação."
            ),
        }
    spec = next((s for s in summary["bySpecialty"] if _norm(s["label"])[:6] in q), None)
    if spec or re.search(r"prazo|vencid|atras", q):
        late = [
            e for e in entries
            if _late(e) > 0 and (not spec or _norm(e["specialty"]) == _norm(spec["label"]))
        ][:5]
        head = (
            f"{spec['label']}: {spec['overdue']} de {spec['total']} pacientes passaram do prazo."
            if spec
            else f"{summary['overdueTotal']} de {summary['total']} pacientes passaram do prazo da sua classe."
        )
        return {
            "text": f"{head} Os primeiros da fila nessa situação:" if late else head,
            "entryIds": [e["id"] for e in late],
        }
    if re.search(r"cancer|oncolog|neoplas", q):
        return {
            "text": (
                f"Há {summary['oncologic']} pacientes com câncer pelo CID. Todos estão acima dos "
                "casos sem urgência, como manda a regra de ouro. Os primeiros:"
            ),
            "entryIds": [e["id"] for e in entries if e["oncologic"]][:4],
        }
    return {"text": NOT_UNDERSTOOD, "suggestions": SUGGESTIONS}
