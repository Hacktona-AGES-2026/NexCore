"""The Neco's texts written by a language model (Gemini), with the rules as fallback.

`init_app` puts a `Neco` in `app.extensions["neco"]`. Without GEMINI_API_KEY
(or with NECO_IA_ENABLED=false) it has no provider and every comment is the
rule-based one — the app, the tests and the demo all work offline.
"""
from .provider import GeminiProvider, ProviderUnavailable, RateGate
from .service import Neco

KEY = "neco"

__all__ = ["GeminiProvider", "KEY", "Neco", "ProviderUnavailable", "RateGate", "init_app"]


def init_app(app):
    provider = None
    config = app.config
    if config.get("NECO_IA_ENABLED") and config.get("GEMINI_API_KEY"):
        try:
            provider = GeminiProvider(
                config["GEMINI_API_KEY"], config["GEMINI_MODEL"], per_minute=config["NECO_IA_RPM"],
            )
            app.logger.info("neco_ia: Gemini %s, %s req/min", config["GEMINI_MODEL"], config["NECO_IA_RPM"])
        except ImportError:
            app.logger.warning("neco_ia: google-genai not installed, using rule-based texts")
    app.extensions[KEY] = Neco(provider)
