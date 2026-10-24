"""The calculations themselves: everything the client can ask over the socket.

Each one is a pure function of the repository and the command's params. The
reads replace the HTTP endpoints one to one; `queue.prioritize` is the slot the
real prioritization algorithm will fill — see its docstring before trusting it.

Payload keys are English; record keys stay the dataset's Portuguese columns.
"""
from . import params as p
from .actions import Progress, action
from ..errors import RequestError

SORT_FIELDS = [
    "dias_em_fila",
    "idade",
    "data_entrada_fila",
    "intensidade_dor_eva",
    "solicitacao_id",
]

#: How many requests to rank between two progress frames.
BATCH = 100


# --- queue reads ----------------------------------------------------------

@action("queue.list")
def list_queue(repository, params, limits):
    page, size = p.pagination(params, limits)
    field = p.text(params, "sort_by") or "dias_em_fila"
    descending = (p.text(params, "order") or "desc") == "desc"

    records = repository.filter(p.queue_filters(params))
    records = repository.sort(records, field, descending)
    return p.paginate(
        records, page, size,
        extras={"sort": {"field": field, "descending": descending}},
    )


@action("queue.request")
def get_request(repository, params, limits):
    request_id = p.required_identifier(params, "request_id")
    record = repository.get_request(request_id)
    if record is None:
        raise RequestError(f"request '{request_id}' not found", 404)

    events = repository.events_for_request(record["solicitacao_id"])
    return {
        "request": record,
        "procedure": repository.get_procedure(record.get("procedimento_id")),
        "events": events,
        "total_events": len(events),
    }


@action("queue.events")
def list_request_events(repository, params, limits):
    request_id = p.required_identifier(params, "request_id")
    if repository.get_request(request_id) is None:
        raise RequestError(f"request '{request_id}' not found", 404)
    page, size = p.pagination(params, limits)
    return p.paginate(repository.events_for_request(request_id), page, size)


@action("patient.events")
def list_patient_events(repository, params, limits):
    patient_id = p.required_identifier(params, "patient_id")
    events = repository.events_for_patient(patient_id)
    if not events:
        raise RequestError(f"no events for patient '{patient_id}'", 404)
    page, size = p.pagination(params, limits)
    return p.paginate(events, page, size)


# --- catalog and references ----------------------------------------------

@action("catalog.procedures")
def procedures(repository, params, limits):
    return {"data": repository.procedures, "total": len(repository.procedures)}


@action("catalog.swalis")
def swalis(repository, params, limits):
    return {"data": repository.swalis, "total": len(repository.swalis)}


@action("catalog.filters")
def filters(repository, params, limits):
    return {
        "specialties": repository.specialties(),
        "priorities": repository.priorities(),
        "sort_fields": SORT_FIELDS,
    }


# --- aggregations ---------------------------------------------------------

@action("stats.summary")
def statistics(repository, params, limits):
    return repository.statistics()


# --- the prioritization slot ---------------------------------------------

#: Marks the payload as *not* the challenge's prioritization rule.
PLACEHOLDER = "placeholder:dias_em_fila"


@action("queue.prioritize")
def prioritize(repository, params, limits):
    """Ranks the queue and streams progress while doing it.

    WARNING: this is the transport's slot, not the prioritization rule. It
    ranks by waiting time alone — the same `sort_by=dias_em_fila` the queue
    already offered — and says so in `strategy`/`provisional`. It ignores the
    golden rule (no oncological patient below one without clinical urgency) and
    would not pass `verificar_fila_priorizada.py`.

    When the real algorithm lands in app/prioritization/ as a pure function, it
    replaces the body here and the client contract does not move: same action,
    same frames, same `solicitacao_id`/`posicao`/`justificativa` keys the
    `fila_priorizada.csv` deliverable needs.
    """
    records = repository.filter(p.queue_filters(params))
    ordered = repository.sort(records, "dias_em_fila", True)
    total = len(ordered)

    ranked = []
    for position, record in enumerate(ordered, start=1):
        days = record.get("dias_em_fila")
        ranked.append(
            {
                "solicitacao_id": record.get("solicitacao_id"),
                "posicao": position,
                "justificativa": (
                    f"provisório: ordenado por tempo de espera ({days} dias em fila)"
                ),
                "nome_paciente": record.get("nome_paciente"),
                "especialidade": record.get("especialidade"),
                "dias_em_fila": days,
                "oncologico_cid": record.get("oncologico_cid"),
                "prioridade_regulacao_norm": record.get("prioridade_regulacao_norm"),
            }
        )
        if position % BATCH == 0 or position == total:
            yield Progress(position, total, "ranqueando a fila")

    return {
        "strategy": PLACEHOLDER,
        "provisional": True,
        "reference_date": repository.reference_date,
        "total": total,
        "data": ranked,
    }
