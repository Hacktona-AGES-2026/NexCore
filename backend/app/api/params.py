"""Reads and validates the query parameters shared by the routes.

Parameter names are English; their accepted values are the dataset's own terms
(priority=alta|media|baixa, sort_by=dias_em_fila), since those are the data.
"""
from flask import current_app, request

from ..data.reader import strip_accents
from ..errors import RequestError

TRUE_VALUES = {"1", "true", "yes", "sim"}
FALSE_VALUES = {"0", "false", "no", "nao", "não"}


def integer(name, default=None, minimum=None, maximum=None):
    raw = request.args.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise RequestError(f"parameter '{name}' must be an integer")
    if minimum is not None and value < minimum:
        raise RequestError(f"parameter '{name}' must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise RequestError(f"parameter '{name}' must be <= {maximum}")
    return value


def boolean(name, default=None):
    raw = request.args.get(name)
    if raw is None or raw.strip() == "":
        return default
    text = raw.strip().lower()
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    raise RequestError(f"parameter '{name}' must be a boolean (yes/no)")


def text(name):
    raw = request.args.get(name)
    if raw is None:
        return None
    raw = raw.strip()
    return strip_accents(raw) if raw else None


def pagination():
    config = current_app.config
    size = integer(
        "size",
        default=config["DEFAULT_PAGE_SIZE"],
        minimum=1,
        maximum=config["MAX_PAGE_SIZE"],
    )
    page = integer("page", default=1, minimum=1)
    return page, size


def queue_filters():
    return {
        "specialty": text("specialty"),
        "priority": text("priority"),
        "city": text("city"),
        "procedure_id": (request.args.get("procedure_id") or "").strip().upper() or None,
        "oncological": boolean("oncological"),
        "min_days": integer("min_days", minimum=0),
        "max_days": integer("max_days", minimum=0),
        "min_age": integer("min_age", minimum=0),
        "search": text("search"),
    }


def paginate(records, page, size, extras=None):
    total = len(records)
    start = (page - 1) * size
    body = {
        "data": records[start : start + size],
        "pagination": {
            "page": page,
            "size": size,
            "total": total,
            "pages": (total + size - 1) // size if size else 0,
        },
    }
    if extras:
        body.update(extras)
    return body
