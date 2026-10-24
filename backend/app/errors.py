"""JSON error handlers, so a client never receives an exception page as HTML."""
from flask import request
from werkzeug.exceptions import HTTPException


class RequestError(Exception):
    """Invalid parameter sent by the client."""

    def __init__(self, message, status=400, details=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.details = details or {}


def _response(message, status, details=None):
    body = {"error": {"message": message, "status": status}}
    if details:
        body["error"]["details"] = details
    return body, status


def register(app):
    @app.errorhandler(RequestError)
    def _request_error(exc):
        return _response(exc.message, exc.status, exc.details)

    @app.errorhandler(HTTPException)
    def _http_error(exc):
        # Routing errors (404/405) fire before any blueprint is matched, so the
        # regulation API's own handler never sees them: keep its {"detail"} shape.
        from .regulation.errors import API_PREFIX, http_detail

        if request.path.startswith(API_PREFIX + "/"):
            return {"detail": http_detail(exc.code)}, exc.code
        return _response(exc.description, exc.code)

    @app.errorhandler(Exception)
    def _unexpected_error(exc):
        app.logger.exception("unhandled error: %s", exc)
        return _response("internal server error", 500)
