"""Validation of the parameters carried by a socket command.

Same rules the HTTP query string enforced, over a plain dict. The difference is
that JSON is typed: `{"size": 10}` arrives as an int and `{"oncological": true}`
as a bool, while a client that sends `"10"` still works. Everything is a pure
function of the dict, so it tests without a socket.

Parameter names are English; their accepted values are the dataset's own terms
(priority=alta|media|baixa, sort_by=dias_em_fila), since those are the data.
"""
from ..data.reader import strip_accents
from ..errors import RequestError

TRUE_VALUES = {"1", "true", "yes", "sim"}
FALSE_VALUES = {"0", "false", "no", "nao", "não"}


def _missing(value):
    return value is None or (isinstance(value, str) and not value.strip())


def integer(params, name, default=None, minimum=None, maximum=None):
    raw = params.get(name)
    if _missing(raw):
        return default
    if isinstance(raw, bool):  # bool is an int in Python; here it is a mistake
        raise RequestError(f"parameter '{name}' must be an integer")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise RequestError(f"parameter '{name}' must be an integer")
    if minimum is not None and value < minimum:
        raise RequestError(f"parameter '{name}' must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise RequestError(f"parameter '{name}' must be <= {maximum}")
    return value


def boolean(params, name, default=None):
    raw = params.get(name)
    if _missing(raw):
        return default
    if isinstance(raw, bool):
        return raw
    text_value = str(raw).strip().lower()
    if text_value in TRUE_VALUES:
        return True
    if text_value in FALSE_VALUES:
        return False
    raise RequestError(f"parameter '{name}' must be a boolean (yes/no)")


def text(params, name):
    raw = params.get(name)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise RequestError(f"parameter '{name}' must be a string")
    raw = raw.strip()
    return strip_accents(raw) if raw else None


def identifier(params, name):
    """Dataset ids are uppercase (SOL-0001, PROC-12): accept any case."""
    raw = params.get(name)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise RequestError(f"parameter '{name}' must be a string")
    return raw.strip().upper() or None


def required_identifier(params, name):
    value = identifier(params, name)
    if value is None:
        raise RequestError(f"parameter '{name}' is required")
    return value


def pagination(params, limits):
    size = integer(
        params, "size",
        default=limits["default_size"], minimum=1, maximum=limits["max_size"],
    )
    page = integer(params, "page", default=1, minimum=1)
    return page, size


def queue_filters(params):
    return {
        "specialty": text(params, "specialty"),
        "priority": text(params, "priority"),
        "city": text(params, "city"),
        "procedure_id": identifier(params, "procedure_id"),
        "oncological": boolean(params, "oncological"),
        "min_days": integer(params, "min_days", minimum=0),
        "max_days": integer(params, "max_days", minimum=0),
        "min_age": integer(params, "min_age", minimum=0),
        "search": text(params, "search"),
    }


def paginate(records, page, size, extras=None):
    total = len(records)
    start = (page - 1) * size
    payload = {
        "data": records[start : start + size],
        "pagination": {
            "page": page,
            "size": size,
            "total": total,
            "pages": (total + size - 1) // size if size else 0,
        },
    }
    if extras:
        payload.update(extras)
    return payload
