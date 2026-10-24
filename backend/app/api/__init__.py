"""Root API blueprint, mounted under /api."""
from flask import Blueprint

api = Blueprint("api", __name__, url_prefix="/api")

from . import catalog, health, queue  # noqa: E402,F401  (registers the routes)
