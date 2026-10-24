"""The Neco's voice: every comment the front shows goes through here.

Each method builds the facts, tries the model, checks the answer and falls
back to the rule-based text. Answers are cached by their facts, so a patient
costs one model call until something about them changes (an event, a manual
move, a validation), and the panels cost one call per change in their numbers.
The result always says where it came from: `source` is "ia" only when the
model answered and passed the number check.
"""
import hashlib
import json
import logging
import threading

from ..regulation import ask as keyword_ask
from . import chat, texts
from .provider import ProviderUnavailable
from .verify import invented_numbers

log = logging.getLogger(__name__)
CACHE_LIMIT = 2000


def _key(kind, facts):
    blob = json.dumps(facts, ensure_ascii=False, sort_keys=True, default=str)
    return kind + ":" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


class Neco:
    def __init__(self, provider=None):
        self.provider = provider
        self._cache = {}
        self._lock = threading.Lock()

    @property
    def enabled(self):
        return self.provider is not None

    # --- cache -----------------------------------------------------------

    def _cached(self, key):
        with self._lock:
            return self._cache.get(key)

    def _store(self, key, value):
        with self._lock:
            if len(self._cache) >= CACHE_LIMIT:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = value
        return value

    # --- one structured comment -------------------------------------------

    def _comment(self, kind, task, schema, facts, rules, render):
        """Model answer if it passes the check, else the rule-based one. Cached by facts."""
        key = _key(kind, facts)
        hit = self._cached(key)
        if hit:
            return hit
        fallback = {**render(rules), "source": "regras", "verified": True}
        if not self.enabled:
            return fallback  # not cached: costs nothing to rebuild
        try:
            answer = self.provider.generate_json(texts.BASE_RULES, texts.as_prompt(task, facts), schema)
            shaped = render(answer)
        except ProviderUnavailable as exc:
            log.warning("neco_ia %s fell back to rules: %s", kind, exc)
            return fallback  # not cached: the next request tries the model again
        except (KeyError, TypeError, AttributeError):
            log.warning("neco_ia %s answer had the wrong shape", kind)
            return fallback
        invented = invented_numbers(shaped["text"] + " " + " ".join(shaped.get("points", [])), facts)
        if invented:
            log.warning("neco_ia %s rejected, numbers not in the facts: %s", kind, sorted(invented))
            return self._store(key, fallback)
        return self._store(key, {**shaped, "source": "ia", "verified": True})

    def explain(self, context):
        """`context` comes from QueueState.explanation_context(rid)."""
        facts = texts.patient_facts(**context)

        def render(answer):
            points = [str(p).strip() for p in answer["points"] if str(p).strip()][:3]
            return {"text": str(answer["headline"]).strip(), "points": points}

        return self._comment("patient", texts.PATIENT_TASK, texts.PATIENT_SCHEMA, facts, texts.patient_rules(facts), render)

    def equity_insight(self, report):
        facts = texts.equity_facts(report)
        return self._comment("equity", texts.EQUITY_TASK, texts.INSIGHT_SCHEMA, facts, texts.equity_rules(facts),
                             lambda a: {"text": str(a["text"]).strip()})

    def impact_insight(self, report):
        facts = texts.impact_facts(report)
        return self._comment("impact", texts.IMPACT_TASK, texts.INSIGHT_SCHEMA, facts, texts.impact_rules(facts),
                             lambda a: {"text": str(a["text"]).strip()})

    # --- conversation -------------------------------------------------------

    def ask(self, question, history, snapshot):
        """NecoAnswer for "Pergunte ao Neco"; the keyword answer when the model is unavailable."""
        entries = snapshot["entries"]

        def keyword():
            return keyword_ask.answer(question, entries, snapshot["summary"], snapshot["equity"], snapshot["pendencies"])

        if not self.enabled:
            return keyword()
        turns = [t for t in (history or []) if t.get("from") in ("me", "neco") and str(t.get("text", "")).strip()]
        try:
            text = self.provider.chat(
                chat.SYSTEM, turns[-chat.HISTORY_TURNS:], question,
                chat.build_tools({**snapshot, "rules": chat.RULES_SUMMARY}),
            )
        except ProviderUnavailable as exc:
            log.warning("neco_ia chat fell back to keywords: %s", exc)
            return keyword()
        answer = {"text": text}
        ids = chat.mentioned_ids(text, entries)
        if ids:
            answer["entryIds"] = ids
        return answer
