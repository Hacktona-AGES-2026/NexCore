from flask import jsonify

from . import api
from . import params
from ..data import current_repository
from ..errors import RequestError


@api.get("/queue")
def list_queue():
    repository = current_repository()
    page, size = params.pagination()
    sort_field = params.text("sort_by") or "dias_em_fila"
    descending = (params.text("order") or "desc") == "desc"

    records = repository.filter(params.queue_filters())
    records = repository.sort(records, sort_field, descending)
    return jsonify(
        params.paginate(
            records,
            page,
            size,
            extras={"sort": {"field": sort_field, "descending": descending}},
        )
    )


@api.get("/queue/<request_id>")
def get_request(request_id):
    repository = current_repository()
    record = repository.get_request(request_id.strip().upper())
    if record is None:
        raise RequestError(f"request '{request_id}' not found", 404)

    events = repository.events_for_request(record["solicitacao_id"])
    return jsonify(
        {
            "request": record,
            "procedure": repository.get_procedure(record.get("procedimento_id")),
            "events": events,
            "total_events": len(events),
        }
    )


@api.get("/queue/<request_id>/events")
def list_request_events(request_id):
    repository = current_repository()
    request_id = request_id.strip().upper()
    if repository.get_request(request_id) is None:
        raise RequestError(f"request '{request_id}' not found", 404)
    page, size = params.pagination()
    events = repository.events_for_request(request_id)
    return jsonify(params.paginate(events, page, size))


@api.get("/patients/<patient_id>/events")
def list_patient_events(patient_id):
    repository = current_repository()
    events = repository.events_for_patient(patient_id.strip().upper())
    if not events:
        raise RequestError(f"no events for patient '{patient_id}'", 404)
    page, size = params.pagination()
    return jsonify(params.paginate(events, page, size))
