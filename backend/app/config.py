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
    # O verificador oficial lê os CSVs DE ORIGEM, não os normalizados.
    VERIFIER_DATASET_DIR = Path(
        os.environ.get("VERIFIER_DATASET_DIR", BACKEND_ROOT / "dataset")
    )
    REFERENCE_DATE = os.environ.get("REFERENCE_DATE", DEFAULT_REFERENCE_DATE)
    AUTO_REFRESH_DATASET = _bool(os.environ.get("AUTO_REFRESH_DATASET"), True)
    DPSS_REACTIVE_ENABLED = _bool(os.environ.get("DPSS_REACTIVE_ENABLED"), True)
    DPSS_WATCH_INTERVAL_SECONDS = float(
        os.environ.get("DPSS_WATCH_INTERVAL_SECONDS", "1.0")
    )
    DEFAULT_PAGE_SIZE = int(os.environ.get("DEFAULT_PAGE_SIZE", "50"))
    MAX_PAGE_SIZE = int(os.environ.get("MAX_PAGE_SIZE", "500"))
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")
    WS_PATH = os.environ.get("WS_PATH", "/ws")
    HOSPITAL_ID = os.environ.get("HOSPITAL_ID", "hsl")
    # Textos do Neco escritos pelo Gemini (plano gratuito). Sem chave, tudo cai no texto por regras.
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
    NECO_IA_ENABLED = _bool(os.environ.get("NECO_IA_ENABLED"), True)
    NECO_IA_RPM = int(os.environ.get("NECO_IA_RPM", "10"))
    TESTING = False
    DEBUG = _bool(os.environ.get("FLASK_DEBUG"))


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "teste"
    DPSS_REACTIVE_ENABLED = False
    # A suíte nunca chama o modelo de verdade, mesmo com a chave no ambiente.
    GEMINI_API_KEY = ""


ENVIRONMENTS = {"desenvolvimento": Config, "teste": TestConfig, "producao": Config}


def get_config(name=None):
    name = name or os.environ.get("APP_AMBIENTE", "desenvolvimento")
    return ENVIRONMENTS.get(name, Config)
