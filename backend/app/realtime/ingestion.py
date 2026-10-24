"""WebSocket commands that ingest source data and trigger reactive DPSS."""
from flask import current_app

from ..errors import RequestError
from .actions import action


def _payload(params, name):
    nested = params.get(name)
    if nested is None:
        return params
    if not isinstance(nested, dict):
        raise RequestError(f"parameter '{name}' must be an object")
    return nested


def _ingestion():
    service = current_app.extensions.get("dataset_ingestion")
    if service is None:
        raise RequestError("dataset ingestion is unavailable", 503)
    return service


@action("queue.request.create")
def create_queue_request(repository, params, limits):
    del repository, limits
    return _ingestion().create_request(_payload(params, "request"))


@action("clinical_event.create")
def create_clinical_event(repository, params, limits):
    del repository, limits
    return _ingestion().create_event(_payload(params, "event"))


@action("procedure.upsert")
def upsert_procedure(repository, params, limits):
    del repository, limits
    return _ingestion().upsert_procedure(_payload(params, "procedure"))

