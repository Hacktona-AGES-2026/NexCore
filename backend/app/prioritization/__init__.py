"""Transparent, auditable surgical-queue prioritization: pure functions, no Flask, no socket.

Two engines live here. The DPS (`dps.calculate_priority`, `dps.prioritize`) feeds the
`queue.prioritize` action through `pipeline`. The Neco (`rules.assess` scores one request,
`ranking.rank` orders them, `ranking.golden_rule_violation` checks the golden rule) feeds
the regulation API.
"""

from .dps import calculate_priority, prioritize
from .dpss import extend_priority as extend_dpss_priority
from .ranking import golden_rule_violation, rank, relocate
from .rules import CLASS_LABEL, CLASSES, DEADLINE_DAYS, FACTOR_MAX, assess, is_overdue

__all__ = [
    "CLASS_LABEL", "CLASSES", "DEADLINE_DAYS", "FACTOR_MAX", "assess",
    "calculate_priority", "extend_dpss_priority", "golden_rule_violation", "is_overdue", "prioritize",
    "rank", "relocate",
]
