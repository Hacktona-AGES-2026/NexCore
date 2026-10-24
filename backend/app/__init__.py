"""Surgical queue prioritization backend (9ª Hackatona · NexCore)."""
import logging

from flask import Flask, jsonify

from . import data, errors, realtime, regulation
from .config import get_config


def create_app(environment=None, **overrides):
    app = Flask(__name__)
    app.config.from_object(get_config(environment))
    app.config.update(overrides)
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    logging.basicConfig(
        level=logging.DEBUG if app.config["DEBUG"] else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    data.init_app(app)
    errors.register(app)

    from .api import api

    app.register_blueprint(api)
    realtime.init_app(app)
    regulation.init_app(app)
    _configure_cors(app)

    @app.get("/")
    def index():
        return jsonify(
            {
                "name": "NexCore API",
                "description": "Surgical queue prioritization — synthetic data",
                "transport": "websocket",
                "websocket": app.config["WS_PATH"],
                "regulation": {
                    "rest": f"{regulation.API_PREFIX}/hospitais/{app.config['HOSPITAL_ID']}",
                    "stream": regulation.STREAM_PATH,
                },
                "protocol": realtime.protocol.PROTOCOL_VERSION,
                "actions": realtime.actions.names(),
                "routes": sorted(
                    str(rule)
                    for rule in app.url_map.iter_rules()
                    if not str(rule).startswith("/static")
                ),
            }
        )

    return app


def _configure_cors(app):
    origins = app.config["CORS_ORIGINS"]

    @app.after_request
    def _headers(response):
        response.headers.setdefault("Access-Control-Allow-Origin", origins)
        response.headers.setdefault(
            "Access-Control-Allow-Headers", "Content-Type, Authorization"
        )
        response.headers.setdefault(
            "Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        )
        return response
