"""Module 1: Dynamic Priority Score (DPS).

The implemented score is ``P = (t / M) * (1 + c)``.  The module intentionally
keeps the evidence, uncertainty and safety constraints alongside the number:
a score without its provenance must not be used to make a clinical decision.

The current generic weights are an explicit *prototype configuration*. They
are not claimed to be PAPRIKA weights. A local PAPRIKA elicitation and
prospective validation are required before clinical use.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Mapping

from ..data.reader import strip_accents

DEFAULT_WEIGHTS = {
    "gravidade_clinica": 1 / 3,
    "dor": 1 / 3,
    "vulnerabilidade_metabolica": 1 / 3,
}
MODEL_VERSION = "0.1.0-prototype"
RULESET_VERSION = "swalis-prototype-2026-10-24"

TERMINAL_PHONE_RESULTS = {"desistiu", "informou_cirurgia_outro_servico"}
ALARM_TERMS = (
    "risco de vida",
    "ameaca a vida",
    "perda de orgao",
    "perda de funcao",
    "angina instavel",
    "estrangul",
    "obstrucao intestinal",
)


def _date(value) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _number(value, minimum=0.0, maximum=1.0):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return max(minimum, min(maximum, parsed))


def _normalized_cid(value):
    """Return a punctuation-free CID code for deterministic prototype rules."""
    return "".join(
        character
        for character in str(value or "").upper()
        if character.isalnum()
    )


def _eligible_events(record, events: Iterable[Mapping], as_of: date):
    request_id = record.get("solicitacao_id")
    patient_id = record.get("paciente_id")
    eligible = []
    rejected = {"future": 0, "duplicate": 0, "inconsistent_link": 0}
    for event in events:
        event_date = _date(event.get("data_evento"))
        if event_date and event_date > as_of:
            rejected["future"] += 1
            continue
        if event.get("duplicata_conteudo") is True:
            rejected["duplicate"] += 1
            continue
        if event.get("solicitacao_na_fila") is False:
            rejected["inconsistent_link"] += 1
            continue
        if event.get("paciente_coincide_fila") is False:
            rejected["inconsistent_link"] += 1
            continue
        if event.get("solicitacao_id") != request_id:
            rejected["inconsistent_link"] += 1
            continue
        if patient_id and event.get("paciente_id") not in {None, patient_id}:
            rejected["inconsistent_link"] += 1
            continue
        eligible.append(event)
    eligible.sort(key=lambda item: item.get("data_evento") or "")
    return eligible, rejected


def _latest(events, event_type):
    matching = [e for e in events if e.get("tipo_evento_norm") == event_type]
    return matching[-1] if matching else None


def _within_days(event, as_of, days):
    event_date = _date(event.get("data_evento"))
    return event_date is not None and 0 <= (as_of - event_date).days <= days


def _format_date(value):
    parsed = _date(value)
    return parsed.strftime("%d/%m/%Y") if parsed else "data não informada"


def _event_reference(event, label):
    if not event:
        return label
    event_id = event.get("evento_id") or "evento sem ID"
    return f"{label} ({event_id}, {_format_date(event.get('data_evento'))})"


def _has_dm(record):
    if record.get("flag_diabetico_norm") is not None:
        return bool(record.get("flag_diabetico_norm"))
    comorbidities = strip_accents(record.get("comorbidades") or "")
    return "diabet" in comorbidities or "dm1" in comorbidities or "dm2" in comorbidities


def build_snapshot(record, events, as_of):
    """Build the time-correct clinical snapshot used by every downstream rule."""
    as_of = _date(as_of)
    if as_of is None:
        raise ValueError("as_of must be a valid ISO date")
    entry = _date(record.get("data_entrada_fila"))
    if entry and entry > as_of:
        raise ValueError("queue entry date cannot be after as_of")
    waiting_days = (as_of - entry).days if entry else record.get("dias_em_fila")

    valid_events, rejected = _eligible_events(record, events, as_of)
    latest_by_type = {
        event_type: _latest(valid_events, event_type)
        for event_type in (
            "contato_telefonico",
            "consulta_reavaliacao",
            "exame_imagem",
            "hba1c",
        )
    }
    recent_er = [
        e
        for e in valid_events
        if e.get("tipo_evento_norm") == "pronto_socorro" and _within_days(e, as_of, 180)
    ]
    recent_admissions = [
        e
        for e in valid_events
        if e.get("tipo_evento_norm") == "internacao" and _within_days(e, as_of, 30)
    ]
    positive_biopsies = [
        e
        for e in valid_events
        if e.get("tipo_evento_norm") == "biopsia"
        and e.get("resultado_norm") == "positivo"
    ]

    latest_hba1c = None
    queue_hba1c_date = _date(record.get("data_hba1c_ultima"))
    queue_hba1c = _number(record.get("hba1c_ultima"), 0, 30)
    if queue_hba1c is not None:
        latest_hba1c = {
            "value": queue_hba1c,
            "date": queue_hba1c_date,
            "source": "fila",
        }
    hba1c_event = latest_by_type["hba1c"]
    if hba1c_event:
        value = _number(hba1c_event.get("valor_numerico"), 0, 30)
        event_date = _date(hba1c_event.get("data_evento"))
        if value is not None and (
            latest_hba1c is None
            or latest_hba1c["date"] is None
            or (event_date and event_date >= latest_hba1c["date"])
        ):
            latest_hba1c = {"value": value, "date": event_date, "source": "evento"}

    latest_phone = latest_by_type["contato_telefonico"]
    active = not (
        latest_phone and latest_phone.get("resultado_norm") in TERMINAL_PHONE_RESULTS
    )
    return {
        "as_of": as_of,
        "entry_date": entry,
        "waiting_days": waiting_days,
        "events": valid_events,
        "rejected_events": rejected,
        "latest_phone": latest_phone,
        "latest_reevaluation": latest_by_type["consulta_reavaliacao"],
        "latest_imaging": latest_by_type["exame_imagem"],
        "positive_biopsy": bool(positive_biopsies),
        "latest_positive_biopsy": positive_biopsies[-1] if positive_biopsies else None,
        "latest_recent_er": recent_er[-1] if recent_er else None,
        "latest_recent_admission": recent_admissions[-1] if recent_admissions else None,
        "recent_er_count": len(recent_er),
        "historical_er_count": sum(
            e.get("tipo_evento_norm") == "pronto_socorro" for e in valid_events
        ),
        "recent_admission_count": len(recent_admissions),
        "historical_admission_count": sum(
            e.get("tipo_evento_norm") == "internacao" for e in valid_events
        ),
        "latest_hba1c": latest_hba1c,
        "active": active,
    }


def infer_swalis(record, snapshot):
    """Conservative, explainable SWALIS classification for the prototype.

    CID identifies malignancy but does not determine SWALIS by itself. Current
    symptoms, functional loss and event trajectory are deliberately included.
    """
    text = strip_accents(
        " ".join(
            str(record.get(field) or "")
            for field in ("cid_descricao", "justificativa_clinica", "observacoes")
        )
    )
    reasons = []
    latest_image = snapshot["latest_imaging"] or {}
    latest_review = snapshot["latest_reevaluation"] or {}
    latest_phone = snapshot["latest_phone"] or {}
    pain = record.get("intensidade_dor_eva")
    limitation = strip_accents(record.get("limitacao_funcional_norm") or "")
    cid = _normalized_cid(record.get("cid_principal"))

    alarm = next((term for term in ALARM_TERMS if term in text), None)
    if alarm:
        reasons.append(f"texto clínico contém o sinal de alarme '{alarm}'")
    if snapshot["recent_admission_count"]:
        reasons.append(
            _event_reference(
                snapshot["latest_recent_admission"],
                "internação registrada nos últimos 30 dias",
            )
        )
    if alarm or snapshot["recent_admission_count"]:
        return "A1", reasons

    oncological = bool(record.get("oncologico_cid"))
    if oncological:
        reasons.append(
            f"CID principal {record.get('cid_principal') or 'não informado'} "
            "identificado como oncológico"
        )
    if snapshot["positive_biopsy"]:
        reasons.append(
            _event_reference(snapshot["latest_positive_biopsy"], "biópsia positiva")
        )
    if latest_image.get("resultado_norm") == "progressao":
        reasons.append(
            _event_reference(latest_image, "imagem mais recente mostra progressão")
        )
    if oncological or snapshot["positive_biopsy"] or reasons:
        return "A2", reasons

    # Local inference rules for diagnoses that occur in the current queue but
    # have no direct SWALIS mapping. They use the diagnosis together with the
    # clinical description; the CID alone is not treated as sufficient evidence
    # of urgency. These are transparent prototype rules, not PAPRIKA weights.
    if cid == "N132" and "hidronefrose" in text and "obstr" in text:
        return "B", [
            "CID N13.2 com obstrução urinária e hidronefrose descritas no pedido"
        ]
    if cid == "E042" and (
        "desvio traqueal" in text or "dispneia" in text or "compress" in text
    ):
        return "B", [
            "bócio multinodular com sinal compressivo respiratório descrito no pedido"
        ]

    if record.get("flag_piora_clinica_norm"):
        reasons.append("campo flag_piora_clinica_norm indica piora")
    if latest_review.get("resultado_norm") == "piora":
        reasons.append(
            _event_reference(
                latest_review, "reavaliação clínica mais recente registra piora"
            )
        )
    if latest_phone.get("resultado_norm") == "relata_piora":
        reasons.append(
            _event_reference(latest_phone, "contato mais recente registra piora")
        )
    if pain is not None and pain >= 7:
        reasons.append(f"dor intensa (EVA {pain})")
    if limitation == "grave":
        reasons.append("limitação funcional grave")
    if snapshot["recent_er_count"] >= 2:
        reasons.append(
            _event_reference(
                snapshot["latest_recent_er"],
                f"{snapshot['recent_er_count']} idas ao pronto-socorro em 180 dias; última",
            )
        )
    if reasons:
        return "B", reasons

    if cid == "K802" and (
        "sintomat" in text or "colica" in text or "colecist" in text
    ):
        return "C", [
            "colelitíase sintomática com cólicas recorrentes descritas no pedido"
        ]
    if cid == "I839" and (
        "ceap c3" in text or "dermatite" in text or "edema" in text
    ):
        return "C", [
            "doença venosa crônica com edema ou alteração cutânea descrita no pedido"
        ]

    if pain is not None and pain >= 4:
        reasons.append(f"dor moderada (EVA {pain})")
    if limitation in {"moderada", "leve"}:
        reasons.append(f"limitação funcional {limitation}")
    if snapshot["recent_er_count"] == 1:
        reasons.append(
            _event_reference(
                snapshot["latest_recent_er"],
                "uma ida ao pronto-socorro em 180 dias",
            )
        )
    if reasons:
        return "C", reasons

    if cid == "K429" and "sem obstrucao" in text and "gangrena" in text:
        return "D", [
            "hérnia umbilical sem obstrução ou gangrena e sem marcador atual de progressão"
        ]

    if pain is not None and pain <= 3 and limitation in {"nenhuma", "leve", ""}:
        return "D", ["sem marcador atual de progressão e baixa carga sintomática"]
    return None, ["dados insuficientes para inferir SWALIS com segurança"]


def _disease_severity(record, snapshot, swalis_class):
    base = {"A1": 1.0, "A2": 0.85, "B": 0.65, "C": 0.4, "D": 0.15}.get(
        swalis_class
    )
    if base is None:
        return None, {}
    asa = _number(record.get("asa"), 1, 5)
    asa_component = (asa - 1) / 4 if asa is not None else None
    clinical = base
    if snapshot["historical_er_count"]:
        clinical = min(1.0, clinical + min(snapshot["historical_er_count"], 3) * 0.03)
    if snapshot["historical_admission_count"]:
        clinical = min(1.0, clinical + 0.05)
    # ASA is vulnerability, not diagnosis severity; it is exposed separately and
    # receives only a provisional 20% share in this composite prototype.
    value = clinical if asa_component is None else 0.8 * clinical + 0.2 * asa_component
    return round(value, 4), {
        "disease_state": round(clinical, 4),
        "asa": asa,
        "asa_vulnerability": round(asa_component, 4) if asa_component is not None else None,
    }


def _metabolic_vulnerability(record, snapshot):
    hba1c = snapshot["latest_hba1c"]
    diabetic = _has_dm(record)
    if hba1c is None:
        return (None if diabetic else 0.0), {
            "diabetic": diabetic,
            "hba1c": None,
            "missing": diabetic,
        }
    value = hba1c["value"]
    if value < 6.5:
        score = 0.1
    elif value <= 7.0:
        score = 0.25
    elif value <= 8.5:
        score = 0.55
    elif value <= 10.0:
        score = 0.8
    else:
        score = 1.0
    return score, {
        "diabetic": diabetic,
        "hba1c": value,
        "hba1c_date": hba1c["date"].isoformat() if hba1c["date"] else None,
        "source": hba1c["source"],
        "requires_preoperative_review": value > 8.5,
    }


def calculate_clinical_factor(record, snapshot, swalis_class, weights=None):
    weights = dict(weights or DEFAULT_WEIGHTS)
    if set(weights) != set(DEFAULT_WEIGHTS):
        raise ValueError(
            "clinical-factor weights must contain exactly: "
            + ", ".join(DEFAULT_WEIGHTS)
        )
    if any(
        not isinstance(value, (int, float)) or value < 0
        for value in weights.values()
    ):
        raise ValueError("clinical-factor weights must be non-negative numbers")
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("clinical-factor weights must sum to a positive value")
    weights = {key: value / total_weight for key, value in weights.items()}

    severity, severity_detail = _disease_severity(record, snapshot, swalis_class)
    pain_raw = _number(record.get("intensidade_dor_eva"), 0, 10)
    pain = pain_raw / 10 if pain_raw is not None else None
    metabolic, metabolic_detail = _metabolic_vulnerability(record, snapshot)
    components = {
        "gravidade_clinica": severity,
        "dor": pain,
        "vulnerabilidade_metabolica": metabolic,
    }
    c_min = sum(weights[name] * (value if value is not None else 0) for name, value in components.items())
    c_max = sum(weights[name] * (value if value is not None else 1) for name, value in components.items())
    c = (c_min + c_max) / 2
    missing = [name for name, value in components.items() if value is None]
    return {
        "value": round(c, 6),
        "minimum": round(c_min, 6),
        "maximum": round(c_max, 6),
        "components": components,
        "details": {
            "gravidade_clinica": severity_detail,
            "vulnerabilidade_metabolica": metabolic_detail,
        },
        "weights": {name: round(value, 6) for name, value in weights.items()},
        "missing_components": missing,
        "uncertain": bool(missing),
        "weight_source": "provisional_equal_weights_not_paprika",
    }


def _data_quality_alerts(record):
    alerts = []
    manual_oncology = record.get("flag_oncologico_norm")
    cid_oncology = record.get("oncologico_cid")
    if manual_oncology is not None and bool(manual_oncology) != bool(cid_oncology):
        alerts.append(
            "divergência entre flag_oncologico_norm e oncologico_cid derivado do CID"
        )
    free_text = strip_accents(
        " ".join(
            str(record.get(field) or "")
            for field in ("justificativa_clinica", "observacoes")
        )
    )
    if "diverg" in free_text or "inconsist" in free_text:
        alerts.append("o texto clínico registra divergência ou inconsistência cadastral")
    return alerts


def _component_text(name, value):
    label = {
        "gravidade_clinica": "gravidade clínica",
        "dor": "dor",
        "vulnerabilidade_metabolica": "vulnerabilidade metabólica",
    }[name]
    return f"{label} não informada" if value is None else f"{label}={value:.4f}"


def build_justification(
    record,
    snapshot,
    swalis_class,
    swalis_reasons,
    deadline,
    clinical_factor,
    score,
    data_quality_alerts,
):
    """Create a deterministic clinical explanation from structured evidence."""
    waiting_days = snapshot["waiting_days"]
    entry = _format_date(snapshot["entry_date"])
    parts = [
        f"A solicitação aguarda {waiting_days} dias desde {entry}."
        if waiting_days is not None
        else "Não foi possível determinar o tempo de espera."
    ]
    if swalis_class and deadline:
        reasons = "; ".join(swalis_reasons)
        parts.append(
            f"Foi classificada como SWALIS {swalis_class}, com prazo máximo de "
            f"{deadline} dias, pelos seguintes motivos: {reasons}."
        )
    else:
        parts.append(
            "A classe SWALIS não foi calculada porque faltam evidências clínicas suficientes."
        )

    components = clinical_factor["components"]
    component_text = ", ".join(
        _component_text(name, components[name])
        for name in (
            "gravidade_clinica",
            "dor",
            "vulnerabilidade_metabolica",
        )
    )
    parts.append(
        f"O fator clínico é c={clinical_factor['value']:.4f}, composto por "
        f"{component_text}."
    )
    if clinical_factor["uncertain"]:
        missing = ", ".join(clinical_factor["missing_components"])
        parts.append(
            f"Há incerteza por ausência de {missing}; o intervalo possível de c é "
            f"{clinical_factor['minimum']:.4f} a {clinical_factor['maximum']:.4f}."
        )

    if score is not None:
        consumed = waiting_days / deadline if waiting_days is not None and deadline else 0
        parts.append(
            f"O prazo consumido é {consumed:.2f} vezes o máximo recomendado e o "
            f"DPS é {score:.4f}, calculado por P=(t/M)×(1+c)."
        )
        band = "faixa de segurança A1/A2" if swalis_class in {"A1", "A2"} else "faixa geral"
        parts.append(f"A solicitação é ordenada na {band} por DPS decrescente.")
    else:
        parts.append("O DPS ficou incompleto e o caso requer revisão humana.")

    if data_quality_alerts:
        parts.append(
            "Revisão necessária por qualidade de dados: "
            + "; ".join(data_quality_alerts)
            + "."
        )
    return " ".join(parts)


def calculate_priority(record, events, swalis_rows, as_of, weights=None):
    snapshot = build_snapshot(record, events, as_of)
    swalis_class, swalis_reasons = infer_swalis(record, snapshot)
    deadlines = {
        row.get("classe_norm") or row.get("classe"): row.get("prazo_maximo_dias")
        for row in swalis_rows
    }
    deadline = deadlines.get(swalis_class)
    if swalis_class is not None and (deadline is None or deadline <= 0):
        raise ValueError(f"invalid or missing SWALIS deadline for class {swalis_class}")
    clinical_factor = calculate_clinical_factor(
        record, snapshot, swalis_class, weights=weights
    )
    waiting_days = snapshot["waiting_days"]
    score = None
    minimum = None
    maximum = None
    if waiting_days is not None and deadline:
        minimum = waiting_days / deadline * (1 + clinical_factor["minimum"])
        maximum = waiting_days / deadline * (1 + clinical_factor["maximum"])
        score = waiting_days / deadline * (1 + clinical_factor["value"])

    event_summary = {
        "considered": len(snapshot["events"]),
        "rejected": snapshot["rejected_events"],
        "recent_er_180d": snapshot["recent_er_count"],
        "historical_er": snapshot["historical_er_count"],
        "recent_admissions_30d": snapshot["recent_admission_count"],
        "historical_admissions": snapshot["historical_admission_count"],
        "positive_biopsy": snapshot["positive_biopsy"],
        "latest_phone_result": (snapshot["latest_phone"] or {}).get("resultado_norm"),
        "latest_reevaluation_result": (snapshot["latest_reevaluation"] or {}).get("resultado_norm"),
        "latest_imaging_result": (snapshot["latest_imaging"] or {}).get("resultado_norm"),
    }
    computed = score is not None
    data_quality_alerts = _data_quality_alerts(record)
    justification = build_justification(
        record,
        snapshot,
        swalis_class,
        swalis_reasons,
        deadline,
        clinical_factor,
        score,
        data_quality_alerts,
    )
    readiness_actions = []
    preanesthesia = record.get("avaliacao_pre_anestesica_norm")
    if preanesthesia in {"pendente", "vencida"}:
        readiness_actions.append(f"avaliacao_pre_anestesica_{preanesthesia}")
    if record.get("exames_pre_op_validos_norm") is False:
        readiness_actions.append("atualizar_exames_pre_operatorios")
    if clinical_factor["details"]["vulnerabilidade_metabolica"].get(
        "requires_preoperative_review", False
    ):
        readiness_actions.append("revisao_metabolica_pre_operatoria")
    return {
        "solicitacao_id": record.get("solicitacao_id"),
        "paciente_id": record.get("paciente_id"),
        "procedimento_id": record.get("procedimento_id"),
        "procedimento": record.get("procedimento"),
        "especialidade": record.get("especialidade"),
        "cid_principal": record.get("cid_principal"),
        "active": snapshot["active"],
        "as_of": snapshot["as_of"].isoformat(),
        "waiting_days": waiting_days,
        "swalis": {
            "class": swalis_class,
            "maximum_wait_days": deadline,
            "reasons": swalis_reasons,
            "source": "swalis_normalizado.csv + regras_clinicas_prototipo",
        },
        "clinical_factor": clinical_factor,
        "dps": {
            "score": round(score, 6) if score is not None else None,
            "minimum": round(minimum, 6) if minimum is not None else None,
            "maximum": round(maximum, 6) if maximum is not None else None,
            "formula": "P = (t / M) * (1 + c)",
            "computed": computed,
        },
        "event_history": event_summary,
        "data_quality": {
            "alerts": data_quality_alerts,
            "has_conflict": bool(data_quality_alerts),
        },
        "operational_readiness": {
            "preanesthesia_status": preanesthesia,
            "preoperative_exams_valid": record.get("exames_pre_op_validos_norm"),
            "actions": readiness_actions,
            "changes_clinical_priority": False,
        },
        "requires_human_review": (
            not computed
            or clinical_factor["uncertain"]
            or bool(data_quality_alerts)
            or clinical_factor["details"]["vulnerabilidade_metabolica"].get(
                "requires_preoperative_review", False
            )
        ),
        "explanation": (
            f"t={waiting_days}; M={deadline}; c={clinical_factor['value']}; "
            f"SWALIS={swalis_class}"
        ),
        "justification": justification,
        "versions": {
            "model": MODEL_VERSION,
            "swalis_rules": RULESET_VERSION,
            "weights": "provisional-equal-v1",
        },
    }


def prioritize(queue, events_by_request, swalis_rows, as_of, weights=None, include_inactive=False):
    """Calculate DPS and return a deterministic, safety-constrained ranking."""
    results = [
        calculate_priority(
            record,
            events_by_request.get(record.get("solicitacao_id"), ()),
            swalis_rows,
            as_of,
            weights=weights,
        )
        for record in queue
    ]
    if not include_inactive:
        results = [item for item in results if item["active"]]

    def key(item):
        # A1/A2 are a transparent safety band. Within it and in the remaining
        # queue, DPS determines order; this avoids a stable low-risk case being
        # placed ahead of a confirmed oncological case solely due to elapsed time.
        protected = item["swalis"]["class"] in {"A1", "A2"}
        score = item["dps"]["score"]
        return (
            not item["active"],
            not protected,
            score is None,
            -(score or 0),
            item["solicitacao_id"] or "",
        )

    results.sort(key=key)
    for position, item in enumerate(results, 1):
        item["position"] = position
        item["ranking_policy"] = "A1/A2 safety band, then descending DPS"
    return results
