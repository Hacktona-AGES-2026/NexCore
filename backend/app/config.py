"""Application configuration, read from the environment with development defaults."""
from pathlib import Path
import os

# backend/app/config.py -> backend/ : dataset/ vive dentro de backend/.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE_DATE = "2026-10-23"


def _bool(value, default=False):
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "sim", "on"}


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-nao-use-em-producao")
    JSON_AS_ASCII = False
    JSON_SORT_KEYS = False

    DATASET_DIR = Path(
        os.environ.get("DATASET_DIR", BACKEND_ROOT / "dataset" / "normalizado")
    )
    REFERENCE_DATE = os.environ.get("REFERENCE_DATE", DEFAULT_REFERENCE_DATE)
    DEFAULT_PAGE_SIZE = int(os.environ.get("DEFAULT_PAGE_SIZE", "50"))
    MAX_PAGE_SIZE = int(os.environ.get("MAX_PAGE_SIZE", "500"))
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")
    TESTING = False
    DEBUG = _bool(os.environ.get("FLASK_DEBUG"))


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "teste"


ENVIRONMENTS = {"desenvolvimento": Config, "teste": TestConfig, "producao": Config}


def get_config(name=None):
    name = name or os.environ.get("APP_AMBIENTE", "desenvolvimento")
    return ENVIRONMENTS.get(name, Config)
