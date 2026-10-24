"""The Neco's assessment of one request: urgency class, index, warnings.

Pure functions of a queue record and its clinical events (both as the
repository returns them: the dataset's Portuguese columns). Nothing here knows
about Flask, the socket or the front's camelCase — `assess` returns plain data
and the transport decides how to spell it.

Class and index follow docs/CONTRATO_BACKEND.md §4.1–4.2 (the prototype's
weights). "No clinical urgency", which the golden rule depends on, follows the
official verifier instead of "class D": it is the verifier that fails the
deliverable.
"""
from datetime import date, timedelta
import re

from . import text

CLASSES = ("A1", "A2", "B", "C", "D")
DEADLINE_DAYS = {"A1": 15, "A2": 21, "B": 60, "C": 180, "D": 360}
CLASS_LABEL = {
    "A1": "Muito urgente",
    "A2": "Urgente",
    "B": "Prioritário",
    "C": "Moderado",
    "D": "Eletivo",
}
URGENCY_POINTS = {"A1": 40, "A2": 34, "B": 22, "C": 12, "D": 4}
FACTOR_MAX = {"urgency": 40, "wait": 25, "events": 20, "symptoms": 12}
LIMITATION_POINTS = {"grave": 4, "moderada": 2.5, "leve": 1}

RECENT_DAYS = 180
UNCERTAIN_CID = re.compile(r"^(D3[7-9]|D4[0-8]|R91)")

#: Verifier's CID_URGENTE: obstruction/instability codes that are never calm.
URGENT_CID = {"I200", "K403", "K400", "K420", "K430", "K800", "N132", "I832"}

LEFT_QUEUE = {
    "desistiu": "Call center informou desistência. Confirme antes de retirar da fila.",
    "informou_cirurgia_outro_servico": (
        "Call center informou cirurgia em outro serviço. Confirme antes de retirar da fila."
    ),
}


def _cid(record):
    return (record.get("cid_principal_norm") or "").upper().replace(".", "")


def _kind(event):
    return event.get("tipo_evento_norm"), event.get("resultado_norm")


def _is_alarming_event(event):
    """The verifier's list of events that rule out "no clinical urgency"."""
    kind, result = _kind(event)
    return (
        kind in ("pronto_socorro", "internacao")
        or (kind == "biopsia" and result == "positivo")
        or (kind == "exame_imagem" and result == "progressao")
        or (kind == "consulta_reavaliacao" and result == "piora")
    )


def clinical_events(events):
    """Events that count: content duplicates are dropped, as the contract asks."""
    return [e for e in events if not e.get("duplicata_conteudo")]


def signals(events, reference_date):
    """What the events say, already deduplicated. `reference_date` is ISO text."""
    since = (date.fromisoformat(reference_date) - timedelta(days=RECENT_DAYS)).isoformat()
    recent_visits = 0
    worsening = 0
    progression = False
    positive_biopsy = False
    left_queue = None
    for event in events:
        kind, result = _kind(event)
        if kind in ("pronto_socorro", "internacao") and (event.get("data_evento") or "") >= since:
            recent_visits += 1
        if result in ("piora", "relata_piora"):
            worsening += 1
        if kind == "exame_imagem" and result == "progressao":
            progression = True
        if kind == "biopsia" and result == "positivo":
            positive_biopsy = True
        if kind == "contato_telefonico" and result in LEFT_QUEUE:
            left_queue = result
    return {
        "recent_visits": recent_visits,
        "worsening": worsening,
        "progression": progression,
        "positive_biopsy": positive_biopsy,
        "left_queue": left_queue,
    }


def urgency_class(record, sig):
    oncological = bool(record.get("oncologico_cid"))
    pain = record.get("intensidade_dor_eva") or 0
    limitation = record.get("limitacao_funcional_norm")
    visits = sig["recent_visits"]
    if oncological and (sig["progression"] or visits > 0):
        return "A1"
    if oncological or sig["positive_biopsy"]:
        return "A2"
    if UNCERTAIN_CID.match(_cid(record)) or pain >= 7 or limitation == "grave" or visits >= 2:
        return "B"
    if pain >= 4 or limitation == "moderada" or visits == 1:
        return "C"
    return "D"


def class_reason(record, cls):
    """Short sentence the front shows after the class label."""
    cid = record.get("cid_principal") or record.get("cid_principal_norm") or "?"
    pain = record.get("intensidade_dor_eva")
    limitation = record.get("limitacao_funcional_norm")
    if cls == "A1":
        return f"câncer confirmado pelo CID {cid} com piora recente"
    if cls == "A2":
        if record.get("oncologico_cid"):
            return f"câncer confirmado pelo CID {cid}"
        return f"há biópsia positiva, embora o CID {cid} ainda não indique câncer"
    if cls == "B":
        if pain is not None and pain >= 7:
            return f"dor intensa ({pain}/10)"
        if limitation == "grave":
            return "limitação funcional grave"
        if UNCERTAIN_CID.match(_cid(record)):
            return "lesão de comportamento incerto"
        return "idas repetidas ao pronto-socorro"
    if cls == "C":
        if pain is not None and pain >= 4:
            return f"dor moderada ({pain}/10)"
        if limitation == "moderada":
            return "limitação funcional moderada"
        return "uma ida recente ao pronto-socorro"
    return "sem dor, limitação ou piora relevantes"


def factors(record, cls, sig):
    """The four parts of the index, unrounded; `score` is their sum."""
    days = record.get("dias_em_fila") or 0
    pain = record.get("intensidade_dor_eva") or 0
    oncological = bool(record.get("oncologico_cid"))
    events = (
        6 * sig["recent_visits"]
        + 4 * sig["worsening"]
        + (8 if sig["progression"] else 0)
        + (6 if sig["positive_biopsy"] and not oncological else 0)
    )
    return {
        "urgency": URGENCY_POINTS[cls],
        "wait": 25 * min(days / DEADLINE_DAYS[cls], 2) / 2,
        "events": min(events, FACTOR_MAX["events"]),
        "symptoms": 0.8 * pain + LIMITATION_POINTS.get(record.get("limitacao_funcional_norm"), 0),
    }


def no_clinical_urgency(record, events):
    """The verifier's conservative definition, over the normalized columns.

    `events` are *all* the request's events, any date: the verifier does not
    look at a window nor drop duplicates (a duplicate cannot change the answer).
    """
    limitation = record.get("limitacao_funcional_norm") or "nenhuma"
    return (
        not record.get("oncologico_cid")
        and (record.get("intensidade_dor_eva") or 0) <= 3
        and limitation in ("nenhuma", "leve")
        and _cid(record) not in URGENT_CID
        and not any(_is_alarming_event(e) for e in events)
        and not text.has_alarm(record.get("justificativa_clinica"))
    )


def _warnings(record, cls, sig, marks):
    warnings = []
    flag = next((h for h in marks if h["kind"] == "red_flag"), None)
    if flag and cls in ("B", "C", "D"):
        source = record.get("justificativa_clinica") if flag["field"] == "clinicalNote" else record.get("observacoes")
        excerpt = (source or "")[flag["start"]:flag["end"]].lower()
        warnings.append({
            "level": "info",
            "text": f'O texto cita "{excerpt}", sinal de gravidade que não está nos campos estruturados.',
        })
    if _cid(record).startswith("I20") and sig["recent_visits"] == 0:
        warnings.append({
            "level": "info",
            "text": "Angina pode ser caso muito urgente. Não recebi eventos que confirmem; vale revisar.",
        })
    manual_flag = record.get("flag_oncologico_norm")
    oncological = bool(record.get("oncologico_cid"))
    if manual_flag is not None and bool(manual_flag) != oncological:
        cid = record.get("cid_principal")
        warnings.append({
            "level": "info",
            "text": (
                f"O cadastro marca câncer, mas o CID {cid} não indica. Usei o CID."
                if manual_flag
                else f"O cadastro não marca câncer, mas o CID {cid} indica. Usei o CID."
            ),
        })
    if sig["left_queue"]:
        warnings.append({"level": "critical", "text": LEFT_QUEUE[sig["left_queue"]]})
    return warnings


def assess(record, events, reference_date):
    """Everything the Neco computes for one request.

    `events` are the request's events as the repository lists them; duplicates
    are dropped here for the class and the index, and kept for the verifier's
    "no clinical urgency" test.
    """
    sig = signals(clinical_events(events), reference_date)
    cls = urgency_class(record, sig)
    parts = factors(record, cls, sig)
    marks = text.highlights(record.get("justificativa_clinica"), record.get("observacoes"))
    return {
        "urgency_class": cls,
        "class_reason": class_reason(record, cls),
        "factors": parts,
        "score": sum(parts.values()),
        "no_urgency": no_clinical_urgency(record, events),
        "oncological": bool(record.get("oncologico_cid")),
        "warnings": _warnings(record, cls, sig, marks),
        "pending_confirmation": sig["left_queue"] is not None,
        "highlights": marks,
        "signals": sig,
    }


def is_overdue(days_waiting, cls):
    return (days_waiting or 0) > DEADLINE_DAYS[cls]
