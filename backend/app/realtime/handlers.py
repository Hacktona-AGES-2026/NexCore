"""The calculations themselves: everything the client can ask over the socket.

Each one is a pure function of the repository and the command's params. The
reads replace the old HTTP endpoints one to one. DPS lives in the separate
``realtime.prioritization`` adapter and the clinical engine remains transport
independent under ``app.prioritization``.

Payload keys are English; record keys stay the dataset's Portuguese columns.
"""
from . import params as p
from .actions import action
from ..errors import RequestError

SORT_FIELDS = [
    "dias_em_fila",
    "idade",
    "data_entrada_fila",
    "intensidade_dor_eva",
    "solicitacao_id",
]

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
