"""The regulation console the front talks to: REST + a push-only WebSocket.

This is docs/CONTRATO_BACKEND.md: camelCase JSON under /v1/hospitais/<id>,
actions over REST, and `/v1/ws` pushing `queue.snapshot` on connect and then
`queue.patch` / `audit.appended` / `pendency.resolved` / `activity` to every
admin connected. It lives beside the older request/response channel at
WS_PATH (app/realtime), which stays for tools and the deliverable.
"""
from flask import request

from .. import data, realtime
from .routes import API_PREFIX, regulation
from .state import QueueState
from .stream import serve

STREAM_PATH = f"{API_PREFIX}/ws"
DPSS_STREAM_PATH = f"{API_PREFIX}/dpss/ws"


def init_app(app):
    """Builds the in-memory queue and registers the routes. Needs realtime first."""
    app.extensions["queue_state"] = QueueState(app.extensions[data.KEY])
    from ..realtime.dpss_live import ReactiveDpss

    reactive_dpss = ReactiveDpss(
        app.extensions[data.KEY],
        app.config["HOSPITAL_ID"],
        source_directory=app.config["VERIFIER_DATASET_DIR"],
        interval_seconds=app.config["DPSS_WATCH_INTERVAL_SECONDS"],
        logger=app.logger,
    )
    app.extensions["reactive_dpss"] = reactive_dpss
    from ..data.ingestion import DatasetIngestion

    app.extensions["dataset_ingestion"] = DatasetIngestion(
        app.config["VERIFIER_DATASET_DIR"], reactive_dpss
    )
    app.register_blueprint(regulation)

    @realtime.sock.route(STREAM_PATH)
    def stream(ws):
        origin = request.headers.get("Origin")
        if not realtime.origin_allowed(origin, app.config["CORS_ORIGINS"]):
            app.logger.warning("stream refused for origin %r", origin)
            return
        hospital = request.args.get("hospital", app.config["HOSPITAL_ID"])
        if hospital != app.config["HOSPITAL_ID"]:
            app.logger.warning("stream refused for hospital %r", hospital)
            return
        state = app.extensions["queue_state"]
        serve(ws, state.subscribe(hospital))

    @realtime.sock.route(DPSS_STREAM_PATH)
    def dpss_stream(ws):
        origin = request.headers.get("Origin")
        if not realtime.origin_allowed(origin, app.config["CORS_ORIGINS"]):
            app.logger.warning("DPSS stream refused for origin %r", origin)
            return
        hospital = request.args.get("hospital", app.config["HOSPITAL_ID"])
        if hospital != app.config["HOSPITAL_ID"]:
            app.logger.warning("DPSS stream refused for hospital %r", hospital)
            return
        serve(ws, reactive_dpss.subscribe())

    if app.config["DPSS_REACTIVE_ENABLED"]:
        reactive_dpss.start()
