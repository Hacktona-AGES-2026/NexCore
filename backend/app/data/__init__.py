"""Access to the repository loaded on the active application."""
from flask import current_app

from .reader import DatasetUnavailable  # noqa: F401  (re-export)
from .repository import Repository

KEY = "repository"


def init_app(app):
    app.extensions[KEY] = Repository(
        app.config["DATASET_DIR"], app.config["REFERENCE_DATE"]
    )
    return app.extensions[KEY]


def current_repository():
    repository = current_app.extensions[KEY]
    if current_app.config.get("AUTO_REFRESH_DATASET", True):
        repository.refresh_if_changed()
    return repository
