from flask import current_app, jsonify

from . import api
from ..data import current_repository


@api.get("/health")
def health():
    repository = current_repository()
    return jsonify(
        {
            "status": "ok",
            "reference_date": current_app.config["REFERENCE_DATE"],
            "dataset": repository.counts(),
        }
    )


@api.get("/statistics")
def statistics():
    return jsonify(current_repository().statistics())
