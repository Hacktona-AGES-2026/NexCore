"""Turning assessments into an order, and checking the golden rule on it.

An order is a plain list of request ids, position = index + 1. Everything here
is a pure function of lists and dicts, so the regulation layer can try a move,
check it and only then commit it.
"""
from .rules import CLASSES

CLASS_RANK = {cls: rank for rank, cls in enumerate(CLASSES)}


def rank(assessments, locked=None):
    """Class first (A1 > ... > D), then score, then input order.

    `assessments` is an ordered mapping id -> assessment; ties keep that order
    (the dataset's), so the result is deterministic. `locked` maps id -> the
    position a human fixed: those ids sit exactly there and the rest flow around.
    """
    locked = locked or {}
    free = [rid for rid in assessments if rid not in locked]
    free.sort(key=lambda rid: (
        CLASS_RANK[assessments[rid]["urgency_class"]], -assessments[rid]["score"],
    ))
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
