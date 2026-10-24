from flask import current_app, jsonify

from . import api
from ..data import current_repository


@api.get("/saude")
def health():
    repository = current_repository()
    return jsonify(
        {
            "status": "ok",
            "data_referencia": current_app.config["REFERENCE_DATE"],
            "dataset": repository.counts(),
        }
    )


@api.get("/estatisticas")
def statistics():
    return jsonify(current_repository().statistics())
