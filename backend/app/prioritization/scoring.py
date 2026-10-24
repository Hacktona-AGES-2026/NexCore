"""The regulation queue's assessment: the Neco's reading, ordered by the DPSS.

`evaluate` is what the regulation queue stores per request. The Neco
(`rules.assess`) still supplies what only it knows — the verifier's "no clinical
urgency", warnings, highlights and the event signals the export cites. The
SWALIS class, its reason, the factors and the score that orders the queue come
from DPS -> DPSS (`dps.calculate_priority`, `dpss.extend_priority`), the same
engine as the `queue.prioritize.dpss` action.

Pure: the reference tables arrive in a `References`, never from Flask.
"""
from dataclasses import dataclass

from . import dps, dpss
from .rules import assess

#: SWALIS classes that form the safety band at the top of the queue.
PROTECTED = ("A1", "A2")


@dataclass(frozen=True)
class References:
    swalis: tuple = ()
    socioeconomic: object = ()  # rows, or a dpss.MunicipalIndex of them
    disease_burden: tuple = ()
    socioeconomic_weight: float = dpss.DEFAULT_SOCIOECONOMIC_WEIGHT

    @classmethod
    def from_repository(cls, repository, socioeconomic_weight=dpss.DEFAULT_SOCIOECONOMIC_WEIGHT):
        return cls(
            tuple(repository.swalis),
            dpss.MunicipalIndex(repository.socioeconomic),
            tuple(repository.disease_burden),
            socioeconomic_weight,
        )


def evaluate(record, events, reference_date, references):
    """`rules.assess` with class, reason, factors and score replaced by the DPSS.

    When the DPS cannot infer a SWALIS class the Neco's class is shown, the
    score stays None (nothing is imputed) and a warning says so; such a request
    goes after every scored one of its band, as in the DPSS ranking.
    """
    neco = assess(record, events, reference_date)
    base = dps.calculate_priority(record, events, references.swalis, reference_date)
    extended = dpss.extend_priority(
        base, record, references.socioeconomic, references.disease_burden,
        references.socioeconomic_weight,
    )
    swalis = extended["swalis"]
    weight = extended["dpss"]["socioeconomic_weight"]
    vulnerability = extended["dpss"]["socioeconomic_vulnerability"]
    waiting, deadline = extended["waiting_days"], swalis["maximum_wait_days"]
    warnings = list(neco["warnings"])

    if swalis["class"] is None:
        urgency_class, reason = neco["urgency_class"], neco["class_reason"]
        warnings.append({
            "level": "info",
            "text": "O DPS não conseguiu inferir a classe SWALIS com segurança; sem índice, fica no fim da faixa.",
        })
    else:
        urgency_class = swalis["class"]
        reason = "; ".join(swalis["reasons"]) or neco["class_reason"]

    return {
        **neco,
        "urgency_class": urgency_class,
        "class_reason": reason,
        "factors": {
            "wait": waiting / deadline if waiting is not None and deadline else 0.0,
            "clinical": extended["clinical_factor"]["value"] or 0.0,
            "social": weight * vulnerability if vulnerability is not None else 0.0,
        },
        "factor_max": {"wait": 1.0, "clinical": 1.0, "social": weight},
        "score": extended["ranking_score"],
        "warnings": warnings,
        "neco": {"urgency_class": neco["urgency_class"], "score": neco["score"]},
        "dpss": {
            "version": dpss.MODEL_VERSION,
            "basis": extended["ranking_basis"],
            "dps": extended["dps"]["score"],
            "dpss": extended["dpss"]["score"],
            "final": extended["burden_adjustment"]["final_score"],
            "socioeconomic_vulnerability": vulnerability,
            "social_source": extended["dpss"]["social_source"],
            "socioeconomic_weight": weight,
        },
    }


def protected(assessment):
    """In the safety band: SWALIS A1/A2 or cancer by CID, never a calm request.

    Every oncological request is in it and no calm one is, so the golden rule
    holds by construction whatever the scores say.
    """
    if assessment["oncological"]:
        return True
    return assessment["urgency_class"] in PROTECTED and not assessment["no_urgency"]
