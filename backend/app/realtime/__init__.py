"""WebSocket channel: one endpoint, JSON frames, calculations over the dataset.

The client opens `WS_PATH` (default /ws), gets a `welcome` frame listing the
actions, and from then on sends `{id, action, params}` commands. Progress of a
long calculation arrives as `progress` frames carrying the same `id`.
"""
from flask import request
from flask_sock import Sock

from ..data import current_repository
from . import actions, protocol  # noqa: F401  (re-exported for create_app)
from . import handlers  # noqa: F401  (importing registers the actions)
from . import prioritization  # noqa: F401  (registers DPS action)
from .channel import serve

sock = Sock()


def init_app(app):
    app.config.setdefault("SOCK_SERVER_OPTIONS", {"ping_interval": 25})
    sock.init_app(app)

    @sock.route(app.config["WS_PATH"])
    def channel(ws):
        # WebSocket handshakes are not covered by CORS, so the browser will
        # happily connect from any page: the Origin check is ours to make.
        origin = request.headers.get("Origin")
        if not origin_allowed(origin, app.config["CORS_ORIGINS"]):
            app.logger.warning("websocket refused for origin %r", origin)
            return
        serve(ws, current_repository(), limits(app.config), app.logger)

    return sock


def limits(config):
    """Runtime limits and safe feature switches exposed to socket actions."""
    return {
        "default_size": config["DEFAULT_PAGE_SIZE"],
        "max_size": config["MAX_PAGE_SIZE"],
        "auto_refresh_dataset": config.get("AUTO_REFRESH_DATASET", True),
    }


def origin_allowed(origin, allowed):
    """True when a browser at `origin` may open the socket.

    `allowed` is the CORS_ORIGINS config: "*" lets anything in (the dev
    default), otherwise a comma-separated list. A missing Origin header means a
    non-browser client (curl, a test, another service), which we accept.
    """
    if origin is None:
        return True
    allowed = (allowed or "").strip()
    if allowed == "*":
        return True
    permitted = {item.strip() for item in allowed.split(",") if item.strip()}
    return origin in permitted
