from flask import current_app, jsonify

from . import api
from ..data import current_repository


@api.get("/health")
def health():
    """Service liveness plus what the loaded dataset holds."""
    return jsonify(
        {
            "status": "ok",
            "reference_date": current_app.config["REFERENCE_DATE"],
            "websocket": current_app.config["WS_PATH"],
            "dataset": current_repository().counts(),
        }
    )
