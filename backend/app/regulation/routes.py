"""REST routes of the regulation console, under /v1/hospitais/<hospital>.

One route per row of docs/CONTRATO_BACKEND.md §2. Each one validates its body,
calls QueueState and returns what the front's `httpBackend` expects. The
ingestion routes (/fila/entradas, /fila/eventos) are not here yet: the front
does not call them.
"""
from functools import partial

from flask import Blueprint, Response, current_app, g, request

from . import verifier
from .errors import API_PREFIX, ContractError, register

regulation = Blueprint("regulation", __name__, url_prefix=f"{API_PREFIX}/hospitais/<hospital>")
register(regulation)


def current_state():
    return current_app.extensions["queue_state"]


@regulation.url_value_preprocessor
def _check_hospital(endpoint, values):
    hospital = (values or {}).pop("hospital", None)
    if hospital != current_app.config["HOSPITAL_ID"]:
        raise ContractError(f"Hospital '{hospital}' não encontrado.", 404)
    g.hospital_id = hospital


def _body():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ContractError("O corpo da requisição deve ser um objeto JSON.")
    return body


@regulation.get("/fila")
def queue_snapshot():
    return current_state().snapshot(g.hospital_id)


@regulation.post("/fila/<request_id>/reordenar")
def reorder(request_id):
    body = _body()
    return current_state().reorder(
        request_id, body.get("position"), body.get("reason"), body.get("justification"),
    )


@regulation.post("/fila/<request_id>/validar")
def validate(request_id):
    return current_state().validate(request_id)


@regulation.get("/auditoria")
def audit_log():
    return current_state().audit_log()


@regulation.get("/pendencias")
def pendency_list():
    return current_state().pendency_list()


@regulation.post("/pendencias/<pendency_id>/resolver")
def resolve_pendency(pendency_id):
    body = _body()
    action = body.get("action")
    if not isinstance(action, str) or not action.strip():
        raise ContractError("Informe a ação ('action').")
    return current_state().resolve(pendency_id, action.strip(), body.get("note"))


@regulation.get("/painel/resumo")
def summary():
    return current_state().summary()


@regulation.get("/painel/equidade")
def equity():
    return current_state().equity()


@regulation.get("/painel/impacto")
def impact():
    verify = partial(verifier.run, dataset_dir=current_app.config["VERIFIER_DATASET_DIR"])
    try:
        return current_state().impact(verify)
    except verifier.VerifierUnavailable as exc:
        current_app.logger.error("official verifier unavailable: %s", exc)
        raise ContractError("O verificador oficial não está disponível neste servidor.", 503) from exc


@regulation.get("/fila/exportar")
def export_queue():
    return Response(
        current_state().export_csv(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{verifier.FILE_NAME}"'},
    )


@regulation.post("/neco/perguntar")
def ask():
    question = _body().get("question")
    if not isinstance(question, str) or not question.strip():
        raise ContractError("Escreva uma pergunta.")
    return current_state().ask(question.strip())
