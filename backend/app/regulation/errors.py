"""Errors of the regulation API, in the shape the front displays.

The front shows `detail` to the user as is, so these messages are Portuguese —
unlike the rest of our errors, which are for developers. A bug still never
leaks: anything unexpected becomes a generic 500.
"""
from flask import current_app
from werkzeug.exceptions import HTTPException

HTTP_DETAIL = {
    400: "Requisição inválida.",
    404: "Recurso não encontrado.",
    405: "Método não permitido para esta rota.",
    415: "Envie o corpo como JSON.",
}
INTERNAL = "Erro interno do servidor."
API_PREFIX = "/v1"


def http_detail(code):
    return HTTP_DETAIL.get(code, "Requisição não atendida.")


class ContractError(Exception):
    def __init__(self, detail, status=400):
        super().__init__(detail)
        self.detail = detail
        self.status = status


def register(blueprint):
    @blueprint.errorhandler(ContractError)
    def _contract_error(exc):
        return {"detail": exc.detail}, exc.status

    @blueprint.errorhandler(HTTPException)
    def _http_error(exc):
        return {"detail": http_detail(exc.code)}, exc.code

    @blueprint.errorhandler(Exception)
    def _unexpected(exc):
        current_app.logger.exception("regulation API failed: %s", exc)
        return {"detail": INTERNAL}, 500
