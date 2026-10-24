"""The only HTTP surface left: a health check, mounted under /api.

Everything a client reads goes over the WebSocket channel (app/realtime/). This
endpoint stays in HTTP on purpose — a load balancer, a deploy script or the
frontend wanting to know the server is up should not have to open a socket.
"""
from flask import Blueprint

api = Blueprint("api", __name__, url_prefix="/api")

from . import health  # noqa: E402,F401  (registers the route)
