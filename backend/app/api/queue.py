from flask import jsonify

from . import api
from . import params
from ..data import current_repository
from ..errors import RequestError


@api.get("/fila")
def list_queue():
    repository = current_repository()
    page, size = params.pagination()
    sort_field = params.text("ordenar_por") or "dias_em_fila"
    descending = (params.text("ordem") or "desc") == "desc"

    records = repository.filter(params.queue_filters())
    records = repository.sort(records, sort_field, descending)
    return jsonify(
        params.paginate(
            records,
            page,
            size,
            extras={"ordenacao": {"campo": sort_field, "descendente": descending}},
        )
    )


@api.get("/fila/<request_id>")
def get_request(request_id):
    repository = current_repository()
    record = repository.get_request(request_id.strip().upper())
    if record is None:
        raise RequestError(f"solicitacao '{request_id}' nao encontrada", 404)

    events = repository.events_for_request(record["solicitacao_id"])
    return jsonify(
        {
            "solicitacao": record,
            "procedimento": repository.get_procedure(record.get("procedimento_id")),
            "eventos": events,
            "total_eventos": len(events),
        }
    )


@api.get("/fila/<request_id>/eventos")
def list_request_events(request_id):
    repository = current_repository()
    request_id = request_id.strip().upper()
    if repository.get_request(request_id) is None:
        raise RequestError(f"solicitacao '{request_id}' nao encontrada", 404)
    page, size = params.pagination()
    events = repository.events_for_request(request_id)
    return jsonify(params.paginate(events, page, size))


@api.get("/pacientes/<patient_id>/eventos")
def list_patient_events(patient_id):
    repository = current_repository()
    events = repository.events_for_patient(patient_id.strip().upper())
    if not events:
        raise RequestError(f"nenhum evento para o paciente '{patient_id}'", 404)
    page, size = params.pagination()
    return jsonify(params.paginate(events, page, size))
