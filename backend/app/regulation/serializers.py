"""Dataset record + assessment -> the front's camelCase `QueueEntry`.

The mapping is docs/CONTRATO_BACKEND.md §3. Optional fields are omitted when
the CSV cell is empty (nothing is imputed); `asa` and `pain` go out as text
because that is how frontend/src/api/types.ts declares them.
"""
from ..prioritization import FACTOR_MAX
from ..prioritization.rules import clinical_events

FACTOR_ORDER = ("urgency", "wait", "events", "symptoms")


def _text(value):
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


def _put(target, key, value):
    if value is not None and value != "":
        target[key] = value


def clinical_event(event):
    out = {
        "date": event.get("data_evento"),
        "type": event.get("tipo_evento_norm") or event.get("tipo_evento"),
        "result": event.get("resultado_norm") or event.get("resultado") or "",
        "description": event.get("descricao") or "",
        "origin": event.get("origem") or "",
    }
    _put(out, "value", _text(event.get("valor_numerico")))
    return out


def queue_entry(record, assessment, events, city=None):
    """Everything about one request except its place in the queue.

    Position, previousPosition and locked are state, added by QueueState.
    """
    entry = {
        "id": record["solicitacao_id"],
        "patientId": record.get("paciente_id"),
        "name": record.get("nome_paciente") or "",
        "sex": (record.get("sexo_norm") or record.get("sexo") or "").upper(),
        "age": record.get("idade"),
        "city": city or record.get("municipio_norm") or "",
        "procedure": record.get("procedimento") or "",
        "specialty": record.get("especialidade") or "",
        "cid": record.get("cid_principal") or "",
        "cidDescription": record.get("cid_descricao") or "",
    }
    _put(entry, "asa", _text(record.get("asa")))
    _put(entry, "comorbidities", record.get("comorbidades"))
    _put(entry, "pain", _text(record.get("intensidade_dor_eva")))
    _put(entry, "limitation", record.get("limitacao_funcional_norm"))
    entry["clinicalNote"] = record.get("justificativa_clinica") or ""
    _put(entry, "regulationNote", record.get("observacoes"))
    entry["enteredAt"] = record.get("data_entrada_fila")
    entry["daysWaiting"] = record.get("dias_em_fila")
    _put(entry, "manualPriority", record.get("prioridade_regulacao_norm"))
    entry["oncologic"] = assessment["oncological"]

    entry["urgencyClass"] = assessment["urgency_class"]
    entry["score"] = round(assessment["score"], 1)
    entry["factors"] = [
        {"key": key, "value": round(assessment["factors"][key], 1), "max": FACTOR_MAX[key]}
        for key in FACTOR_ORDER
    ]
    entry["classReason"] = assessment["class_reason"]
    entry["warnings"] = [dict(w) for w in assessment["warnings"]]
    entry["pendingConfirmation"] = assessment["pending_confirmation"]
    entry["events"] = [clinical_event(e) for e in clinical_events(events)]
    entry["highlights"] = [dict(h) for h in assessment["highlights"]]
    return entry


def initials(name):
    """"Eliane Lima Peixoto" -> "E.L.P.": the public screen never shows names."""
    return "".join(f"{part[0].upper()}." for part in (name or "").split() if part)
