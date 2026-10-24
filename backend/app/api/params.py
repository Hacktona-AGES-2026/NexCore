"""Reads and validates the query parameters shared by the routes.

Parameter names are part of the public API and stay in Portuguese.
"""
from flask import current_app, request

from ..data.reader import strip_accents
from ..errors import RequestError

TRUE_VALUES = {"1", "true", "sim", "yes"}
FALSE_VALUES = {"0", "false", "nao", "não", "no"}


def integer(name, default=None, minimum=None, maximum=None):
    raw = request.args.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise RequestError(f"parametro '{name}' deve ser um numero inteiro")
    if minimum is not None and value < minimum:
        raise RequestError(f"parametro '{name}' deve ser >= {minimum}")
    if maximum is not None and value > maximum:
        raise RequestError(f"parametro '{name}' deve ser <= {maximum}")
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
    raise RequestError(f"parametro '{name}' deve ser booleano (sim/nao)")


def text(name):
    raw = request.args.get(name)
    if raw is None:
        return None
    raw = raw.strip()
    return strip_accents(raw) if raw else None


def pagination():
    config = current_app.config
    size = integer(
        "tamanho",
        default=config["DEFAULT_PAGE_SIZE"],
        minimum=1,
        maximum=config["MAX_PAGE_SIZE"],
    )
    page = integer("pagina", default=1, minimum=1)
    return page, size


def queue_filters():
    return {
        "especialidade": text("especialidade"),
        "prioridade": text("prioridade"),
        "municipio": text("municipio"),
        "procedimento_id": (request.args.get("procedimento_id") or "").strip().upper()
        or None,
        "oncologico": boolean("oncologico"),
        "dias_minimo": integer("dias_minimo", minimum=0),
        "dias_maximo": integer("dias_maximo", minimum=0),
        "idade_minima": integer("idade_minima", minimum=0),
        "busca": text("busca"),
    }


def paginate(records, page, size, extras=None):
    total = len(records)
    start = (page - 1) * size
    body = {
        "dados": records[start : start + size],
        "paginacao": {
            "pagina": page,
            "tamanho": size,
            "total": total,
            "paginas": (total + size - 1) // size if size else 0,
        },
    }
    if extras:
        body.update(extras)
    return body
