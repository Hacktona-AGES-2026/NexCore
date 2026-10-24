"""Turning assessments into an order, and checking the golden rule on it.

An order is a plain list of request ids, position = index + 1. Everything here
is a pure function of lists and dicts, so the regulation layer can try a move,
check it and only then commit it.
"""
from .scoring import protected


def priority_key(assessment):
    """Smaller goes first: the safety band, then the DPSS score, highest first.

    A request without a score goes after every scored one of its band.
    """
    score = assessment["score"]
    return (not protected(assessment), score is None, -(score or 0))


def rank(assessments, locked=None):
    """Safety band (A1/A2 and cancer) first, then the DPSS score, then input order.

    `assessments` is an ordered mapping id -> assessment; ties keep that order
    (the dataset's), so the result is deterministic. `locked` maps id -> the
    position a human fixed: those ids sit exactly there and the rest flow around.
    """
    locked = locked or {}
    free = [rid for rid in assessments if rid not in locked]
    free.sort(key=lambda rid: priority_key(assessments[rid]))
    order = list(free)
    for rid, position in sorted(locked.items(), key=lambda item: item[1]):
        if rid in assessments:
            order.insert(max(0, min(position - 1, len(order))), rid)
    return order


def relocate(order, request_id, position):
    """A copy of `order` with `request_id` moved to 1-based `position`."""
    moved = [rid for rid in order if rid != request_id]
    moved.insert(max(0, min(position - 1, len(moved))), request_id)
    return moved


def place(order, assessments, request_id):
    """A copy of `order` with `request_id` (re)inserted where its assessment fits.

    The others keep their relative order, manual moves included, so the order
    may not be sorted. The request goes where it disagrees with the fewest of
    them (`priority_key`): the fewest who rank lower above it plus who rank
    higher or equal below it (equals were there first). A human moving one
    patient far up or down then shifts the newcomer by one place at most,
    instead of dragging it along. Ties go to the highest such place: the
    benefit of the doubt is the patient's. The golden rule wins over the fit: an
    oncological request never lands below a calm one, nor a calm one above an
    oncological one.
    """
    rest = [rid for rid in order if rid != request_id]
    a = assessments[request_id]
    key = priority_key(a)
    others = [priority_key(assessments[r]) for r in rest]
    disagreements = sum(1 for k in others if k <= key)  # index 0: all who go first are below
    best, index = disagreements, 0
    for i, k in enumerate(others, start=1):
        disagreements += (k > key) - (k <= key)
        if disagreements < best:
            best, index = disagreements, i
    if a["oncological"]:
        first_calm = next((i for i, rid in enumerate(rest) if assessments[rid]["no_urgency"]), len(rest))
        index = min(index, first_calm)
    if a["no_urgency"]:
        last_onco = max((i for i, rid in enumerate(rest) if assessments[rid]["oncological"]), default=-1)
        index = max(index, last_onco + 1)
    return rest[:index] + [request_id] + rest[index:]


def golden_rule_violation(order, assessments):
    """First breach of the golden rule, or None.

    Returns (oncological_id, calm_id): an oncological request placed below the
    first request with no clinical urgency — the verifier's exact check.
    """
    calm = None
    for rid in order:
        a = assessments[rid]
        if calm is None and a["no_urgency"]:
            calm = rid
        elif calm is not None and a["oncological"]:
            return rid, calm
    return None
