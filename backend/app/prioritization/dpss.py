"""Experimental DPSS extension over the audited DPS result.

DPSS = (T / M) * (1 + c + w*S)
final_score = DPSS * disability_weight

The 0..1 health-state value is called a disability weight, not a DALY.  DALY
is measured in lost healthy years (YLL + YLD).  ``daly_weight_norm`` is accepted
only as a legacy input alias so a prepared table can be migrated explicitly.

The queue carries a precomputed hybrid S: 80% social vulnerability (EVFAM-BR,
with municipal INSE and then 0.5 as fallbacks) plus 20% geographic access
barrier. Each fallback is explicitly marked. Other missing reference data is
not silently imputed. Each request exposes the stage and provenance used for
ranking.
"""
from __future__ import annotations

import math

from ..data.reader import strip_accents

MODEL_VERSION = "0.2.0-experimental"
DEFAULT_SOCIOECONOMIC_WEIGHT = 0.25
MAX_SOCIOECONOMIC_WEIGHT = 1.0
DEFAULT_SOCIOECONOMIC_FALLBACK = 0.5
DEFAULT_DISTANCE_CEILING_KM = 150.0
SOCIAL_SHARE = 0.8
GEOGRAPHIC_SHARE = 0.2
EVFAM_FIELDS = (
    ("evfam_dificuldade_financeira", "dificuldade_financeira"),
    (
        "evfam_uso_medicamentos_continuos",
        "evfam_uso_continuo_medicamentos",
        "uso_continuo_medicamentos",
    ),
    (
        "evfam_sem_apoio_familiar",
        "evfam_ausencia_apoio_familiar",
        "ausencia_apoio_familiar",
    ),
    ("evfam_vulnerabilidade_habitacional", "vulnerabilidade_habitacional"),
)


def _number(value, minimum=0.0, maximum=1.0):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or not minimum <= parsed <= maximum:
        return None
    return parsed


def _city(value):
    return strip_accents(value or "").strip()


def _cid(value):
    return "".join(character for character in str(value or "").upper() if character.isalnum())


def _evfam_number(value):
    raw = "" if value is None else str(value)
    text = strip_accents(raw).strip()
    categorical = {
        "sim": 1.0,
        "true": 1.0,
        "nao": 0.0,
        "false": 0.0,
    }
    if text in categorical:
        return categorical[text]
    return _number(raw.replace(",", "."))


def _evfam_values(record):
    values = []
    columns = []
    for aliases in EVFAM_FIELDS:
        column = next((name for name in aliases if name in record), None)
        if column is None:
            continue
        value = _evfam_number(record.get(column))
        if value is not None:
            values.append(value)
            columns.append(column)
    return values, columns


def _row_code(row):
    return str(row.get("id_municipio") or row.get("codigo_ibge") or "").strip()


def _row_state(row):
    return str(row.get("uf") or "").strip().upper()


class MunicipalIndex:
    """Municipal rows indexed by IBGE code and by accent-free city name.

    Built once per table: matching a request then costs a dict lookup instead of
    a pass over every municipality of Brazil. The matching rule is unchanged.
    """

    def __init__(self, rows):
        self.rows = tuple(rows)
        self.by_code = {}
        self.by_city = {}
        for row in self.rows:
            code = _row_code(row)
            if code:
                self.by_code.setdefault(code, []).append(row)
            city = _city(row.get("municipio_norm") or row.get("municipio"))
            if city:
                self.by_city.setdefault(city, []).append(row)

    def __len__(self):
        return len(self.rows)

    def __iter__(self):
        return iter(self.rows)

    def candidates(self, code, city):
        if code:
            return self.by_code.get(code, [])
        return self.by_city.get(city, []) if city else []


def municipal_index(rows):
    return rows if isinstance(rows, MunicipalIndex) else MunicipalIndex(rows)


def _municipal_reference(record, rows):
    """Return one unambiguous municipal INSE reference for the request."""
    code = str(
        record.get("id_municipio") or record.get("codigo_ibge") or ""
    ).strip()
    city = _city(record.get("municipio_norm") or record.get("municipio"))
    state = str(record.get("uf") or "").strip().upper()
    matches = [
        row for row in municipal_index(rows).candidates(code, city)
        if code or not state or not _row_state(row) or _row_state(row) == state
    ]
    if len(matches) > 1:
        return None, "ambiguous"
    if not matches:
        return None, "not_found"
    value = _number(matches[0].get("s_vulnerabilidade"))
    if value is None:
        return None, "invalid_value"
    return {**matches[0], "_value": value}, None


def _socioeconomic_reference(record, rows):
    """Recalculate S for every execution, never trusting a materialized final S."""
    evfam, evfam_columns = _evfam_values(record)
    municipal, municipal_error = _municipal_reference(record, rows)
    if municipal_error == "ambiguous":
        return None, municipal_error

    if evfam:
        social = sum(evfam) / len(evfam)
        social_source = "evfam_br"
        social_fallback = False
        error = None
    elif municipal is not None:
        social = municipal["_value"]
        social_source = "ibge_inse"
        social_fallback = False
        error = None
    else:
        social = DEFAULT_SOCIOECONOMIC_FALLBACK
        social_source = "fallback_0.5"
        social_fallback = True
        error = "fallback_default_0_5"

    try:
        distance = float(record.get("distancia_hospital_km"))
    except (TypeError, ValueError):
        distance = None
    invalid_distance = (
        distance is None or not math.isfinite(distance) or distance < 0
    )
    geographic = (
        DEFAULT_SOCIOECONOMIC_FALLBACK
        if invalid_distance
        else min(distance / DEFAULT_DISTANCE_CEILING_KM, 1.0)
    )
    vulnerability = min(
        max(SOCIAL_SHARE * social + GEOGRAPHIC_SHARE * geographic, 0.0),
        1.0,
    )
    provenance = municipal or {}
    return {
        **provenance,
        "id_municipio": record.get("id_municipio"),
        "s_vulnerabilidade": vulnerability,
        "s_evfam": sum(evfam) / len(evfam) if evfam else None,
        "s_evfam_colunas_utilizadas": ";".join(evfam_columns),
        "s_social": social,
        "s_social_source": social_source,
        "s_geografico": geographic,
        "s_distancia_teto_km": DEFAULT_DISTANCE_CEILING_KM,
        "s_distancia_imputada": invalid_distance,
        "source": "runtime_hybrid_EVFAM_INSE_distance",
        "_fallback": social_fallback,
    }, error


def _burden_reference(record, rows):
    cid = _cid(record.get("cid_principal_norm") or record.get("cid_principal"))
    candidates = []
    for row in rows:
        prefix = _cid(
            row.get("cid_prefix_norm")
            or row.get("cid_principal_norm")
            or row.get("cid_prefix")
        )
        if prefix and cid.startswith(prefix):
            candidates.append((len(prefix), row))
    if not candidates:
        return None, "not_found"
    longest = max(length for length, _ in candidates)
    matches = [row for length, row in candidates if length == longest]
    if len(matches) != 1:
        return None, "ambiguous"
    raw = matches[0].get("disability_weight_norm")
    legacy_name = False
    if raw is None:
        raw = matches[0].get("daly_weight_norm")
        legacy_name = raw is not None
    value = _number(raw)
    if value is None:
        return None, "invalid_value"
    return {**matches[0], "_value": value, "_legacy_name": legacy_name}, None


def extend_priority(
    dps_priority,
    record,
    socioeconomic_rows=(),
    disease_burden_rows=(),
    socioeconomic_weight=DEFAULT_SOCIOECONOMIC_WEIGHT,
):
    """Add DPSS evidence and scores to one already-calculated DPS result."""
    weight = _number(
        socioeconomic_weight,
        minimum=0.0,
        maximum=MAX_SOCIOECONOMIC_WEIGHT,
    )
    if weight is None:
        raise ValueError("socioeconomic weight must be between 0 and 1")

    socioeconomic, socioeconomic_error = _socioeconomic_reference(
        record, socioeconomic_rows
    )
    burden, burden_error = _burden_reference(record, disease_burden_rows)
    vulnerability = (
        _number(socioeconomic.get("s_vulnerabilidade")) if socioeconomic else None
    )
    disability_weight = burden.get("_value") if burden else None
    socioeconomic_fallback = bool(socioeconomic and socioeconomic.get("_fallback"))
    geographic_fallback = bool(
        socioeconomic and socioeconomic.get("s_distancia_imputada")
    )

    waiting_days = dps_priority.get("waiting_days")
    maximum_wait = dps_priority.get("swalis", {}).get("maximum_wait_days")
    clinical_factor = dps_priority.get("clinical_factor", {}).get("value")
    dps_score = dps_priority.get("dps", {}).get("score")

    dpss_score = None
    if (
        waiting_days is not None
        and maximum_wait
        and clinical_factor is not None
        and vulnerability is not None
    ):
        dpss_score = (waiting_days / maximum_wait) * (
            1 + clinical_factor + weight * vulnerability
        )

    final_score = (
        dpss_score * disability_weight
        if dpss_score is not None and disability_weight is not None
        else None
    )
    if final_score is not None:
        ranking_score = final_score
        ranking_basis = "final_score"
    elif dpss_score is not None:
        ranking_score = dpss_score
        ranking_basis = "dpss_without_disability_weight"
    else:
        ranking_score = dps_score
        ranking_basis = "dps_fallback"

    missing = []
    if vulnerability is None:
        missing.append("socioeconomic_reference")
    elif socioeconomic_fallback:
        missing.append("socioeconomic_reference_fallback_0.5")
    if geographic_fallback:
        missing.append("geographic_distance_fallback_0.5")
    if disability_weight is None:
        missing.append("disability_weight_reference")
    alerts = list(dps_priority.get("data_quality", {}).get("alerts", []))
    if socioeconomic_error:
        alerts.append(f"socioeconomic reference: {socioeconomic_error}")
    if burden_error:
        alerts.append(f"disability weight reference: {burden_error}")
    if burden and burden.get("_legacy_name"):
        alerts.append(
            "legacy column daly_weight_norm interpreted as disability_weight_norm"
        )

    explanation = list(dps_priority.get("explanation", "").splitlines())
    if dpss_score is not None:
        explanation.append(
            f"DPSS={dpss_score:.6f}; S={vulnerability:.6f}; w={weight:.6f}"
        )
    else:
        explanation.append("DPSS not computed: socioeconomic reference unavailable")
    if final_score is not None:
        explanation.append(
            f"final_score={final_score:.6f}; disability_weight={disability_weight:.6f}"
        )
    else:
        explanation.append("final score not computed: disability weight unavailable")

    justification = dps_priority.get("justification", "")
    if dpss_score is not None:
        justification += (
            f" O DPSS é {dpss_score:.4f}, usando vulnerabilidade territorial "
            f"S={vulnerability:.4f} e peso w={weight:.4f}."
        )
        if socioeconomic_fallback:
            justification += (
                " A camada social de S usa o fallback neutro 0,5 porque não há "
                "EVFAM-BR válida nem INSE municipal disponível."
            )
        social = _number(socioeconomic.get("s_social")) if socioeconomic else None
        geographic = (
            _number(socioeconomic.get("s_geografico")) if socioeconomic else None
        )
        if social is not None and geographic is not None:
            justification += (
                f" O S híbrido combina 80% da camada social ({social:.4f}, fonte "
                f"{socioeconomic.get('s_social_source')}) e 20% da barreira "
                f"geográfica ({geographic:.4f})."
            )
        if geographic_fallback:
            justification += " A distância ausente usa fator geográfico neutro 0,5."
    else:
        justification += (
            " O DPSS socioeconômico não foi calculado porque não há uma referência "
            "territorial única e válida para o município; a ordenação usa o DPS."
        )
    if final_score is not None:
        justification += (
            f" O score experimental final é {final_score:.4f}, após aplicar o "
            f"disability weight {disability_weight:.4f}."
        )
    else:
        justification += (
            " O multiplicador de incapacidade não foi aplicado porque o CID não "
            "possui mapeamento validado; nenhum valor foi imputado."
        )

    result = dict(dps_priority)
    result.update(
        {
            "dpss": {
                "score": round(dpss_score, 6) if dpss_score is not None else None,
                "formula": "(T / M) * (1 + c + w*S)",
                "socioeconomic_weight": weight,
                "socioeconomic_vulnerability": vulnerability,
                "social_vulnerability": (
                    _number(socioeconomic.get("s_social")) if socioeconomic else None
                ),
                "social_source": (
                    socioeconomic.get("s_social_source") if socioeconomic else None
                ),
                "geographic_access_barrier": (
                    _number(socioeconomic.get("s_geografico"))
                    if socioeconomic
                    else None
                ),
                "distance_ceiling_km": (
                    socioeconomic.get("s_distancia_teto_km")
                    if socioeconomic
                    else None
                ),
                "computed": dpss_score is not None,
            },
            "burden_adjustment": {
                "disability_weight": disability_weight,
                "final_score": round(final_score, 6) if final_score is not None else None,
                "formula": "DPSS * disability_weight",
                "computed": final_score is not None,
                "terminology": "disability_weight_not_DALY",
            },
            "ranking_score": round(ranking_score, 6) if ranking_score is not None else None,
            "ranking_basis": ranking_basis,
            "reference_coverage": {
                "complete": not missing,
                "missing": missing,
                "socioeconomic_source": (
                    socioeconomic.get("source_version") or socioeconomic.get("source")
                    if socioeconomic
                    else None
                ),
                "burden_source": (
                    burden.get("source_version") or burden.get("source")
                    if burden
                    else None
                ),
                "socioeconomic_fallback": socioeconomic_fallback,
                "geographic_fallback": geographic_fallback,
            },
            "data_quality": {"alerts": alerts, "has_conflict": bool(alerts)},
            "requires_human_review": bool(
                dps_priority.get("requires_human_review") or missing or alerts
            ),
            "explanation": "\n".join(explanation),
            "justification": justification.strip(),
            "versions": {
                **dps_priority.get("versions", {}),
                "dpss": MODEL_VERSION,
            },
        }
    )
    return result


def prioritize(
    dps_ranking,
    queue,
    socioeconomic_rows=(),
    disease_burden_rows=(),
    socioeconomic_weight=DEFAULT_SOCIOECONOMIC_WEIGHT,
):
    """Extend and rank DPS records, retaining the existing A1/A2 safety band."""
    queue_by_id = {row.get("solicitacao_id"): row for row in queue}
    socioeconomic_rows = municipal_index(socioeconomic_rows)
    results = [
        extend_priority(
            item,
            queue_by_id.get(item.get("solicitacao_id"), {}),
            socioeconomic_rows,
            disease_burden_rows,
            socioeconomic_weight,
        )
        for item in dps_ranking
    ]

    def key(item):
        protected = item.get("swalis", {}).get("class") in {"A1", "A2"}
        score = item.get("ranking_score")
        return (
            not item.get("active"),
            not protected,
            score is None,
            -(score or 0),
            item.get("solicitacao_id") or "",
        )

    results.sort(key=key)
    for position, item in enumerate(results, 1):
        item["position"] = position
        item["ranking_policy"] = (
            "A1/A2 safety band, then descending best available DPSS stage"
        )
    return results
