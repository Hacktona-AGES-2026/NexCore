"""Transparent, auditable surgical-queue prioritization: pure functions, no Flask, no socket.

Two engines live here. The DPS (`dps.calculate_priority`, `dps.prioritize`) feeds the
`queue.prioritize` action through `pipeline`. The regulation API's queue is the Neco's
reading ordered by the DPSS: `scoring.evaluate` assesses one request (`rules.assess` plus
DPS -> DPSS), `ranking.rank` orders them (A1/A2 band, then DPSS score) and
`ranking.golden_rule_violation` checks the golden rule.
"""

from .dps import calculate_priority, prioritize
from .dpss import extend_priority as extend_dpss_priority
from .ranking import golden_rule_violation, place, priority_key, rank, relocate
from .rules import CLASS_LABEL, CLASSES, DEADLINE_DAYS, assess, is_overdue
from .scoring import References, evaluate, protected

__all__ = [
    "CLASS_LABEL", "CLASSES", "DEADLINE_DAYS", "References", "assess",
    "calculate_priority", "evaluate", "extend_dpss_priority", "golden_rule_violation", "is_overdue",
    "place", "prioritize", "priority_key", "protected",
    "rank", "relocate",
]
