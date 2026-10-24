"""JSON error handlers, so a client never receives an exception page as HTML.

The response body keeps the Portuguese keys the frontend already consumes:
{"erro": {"mensagem": ..., "status": ..., "detalhes": ...}}.
"""
from werkzeug.exceptions import HTTPException


class RequestError(Exception):
    """Invalid parameter sent by the client."""

    def __init__(self, message, status=400, details=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.details = details or {}


def _response(message, status, details=None):
    body = {"erro": {"mensagem": message, "status": status}}
    if details:
        body["erro"]["detalhes"] = details
    return body, status


def register(app):
    @app.errorhandler(RequestError)
    def _request_error(exc):
        return _response(exc.message, exc.status, exc.details)

    @app.errorhandler(HTTPException)
    def _http_error(exc):
        return _response(exc.description, exc.code)

    @app.errorhandler(Exception)
    def _unexpected_error(exc):
        app.logger.exception("unhandled error: %s", exc)
        return _response("erro interno do servidor", 500)
