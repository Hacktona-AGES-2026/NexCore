"""The language model behind the Neco's texts, behind one small interface.

`GeminiProvider` talks to Google's Gemini API (free tier). Everything else in
`neco_ia` only sees `generate_json` and `chat`, so swapping the model, the plan
or the vendor means writing another class with these two methods — and the
tests use a fake one, with no network and no quota.

Any failure (no key, quota, timeout, bad JSON, vendor down) becomes
`ProviderUnavailable`: the caller falls back to the rule-based text, so the
admin never sees an error because of the model.
"""
import json
from collections import deque
import threading
import time


class ProviderUnavailable(Exception):
    """The model could not answer now; use the rule-based text instead."""


class RateGate:
    """At most `per_minute` calls in any 60-second window (the free tier's limit).

    Calls go out immediately while the window has room, so a page that needs
    two or three texts at once gets them all. When the window is full, a caller
    waits for the oldest call to age out, but only up to `max_wait` seconds;
    past that it gives up (ProviderUnavailable) and the rule-based text is
    shown right away, which beats a screen hanging on a quota.
    """

    WINDOW = 60.0

    def __init__(self, per_minute, max_wait=3.0, clock=time.monotonic, sleep=time.sleep):
        self.per_minute = per_minute
        self.max_wait = max_wait
        self._clock = clock
        self._sleep = sleep
        self._calls = deque()
        self._lock = threading.Lock()

    def acquire(self):
        if self.per_minute <= 0:
            return
        with self._lock:
            now = self._clock()
            while self._calls and now - self._calls[0] >= self.WINDOW:
                self._calls.popleft()
            wait = 0.0
            if len(self._calls) >= self.per_minute:
                wait = self._calls[0] + self.WINDOW - now
                if wait > self.max_wait:
                    raise ProviderUnavailable("rate limit reached")
                self._calls.popleft()
            self._calls.append(now + wait)
        if wait:
            self._sleep(wait)


class GeminiProvider:
    def __init__(self, api_key, model, per_minute=10, timeout_seconds=15):
        # Imported here: the app (and the test suite) runs without the package
        # when no key is configured.
        from google import genai
        from google.genai import errors, types

        self._types = types
        self._errors = errors
        self.model = model
        self._client = genai.Client(
            api_key=api_key, http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)),
        )
        self._gate = RateGate(per_minute)

    def _guarded(self, call):
        self._gate.acquire()
        try:
            return call()
        except self._errors.APIError as exc:
            if exc.code == 404:
                # The usual cause: the model was retired or is not on this key's plan.
                raise ProviderUnavailable(f"gemini 404: model '{self.model}' not available; set GEMINI_MODEL") from exc
            raise ProviderUnavailable(f"gemini {exc.code}") from exc
        except Exception as exc:  # noqa: BLE001  (network, timeout, SDK bugs: all mean "not now")
            raise ProviderUnavailable(type(exc).__name__) from exc

    def _call(self, contents, config):
        return self._guarded(lambda: self._client.models.generate_content(model=self.model, contents=contents, config=config))

    def generate_json(self, system, prompt, schema):
        """One answer constrained to `schema` (a JSON Schema dict)."""
        config = self._types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=schema,
            temperature=0.2,
            max_output_tokens=2048,
        )
        response = self._call(prompt, config)
        try:
            return json.loads(response.text or "")
        except (TypeError, ValueError) as exc:
            raise ProviderUnavailable("invalid json") from exc

    def chat(self, system, history, question, tools, max_tool_calls=6):
        """A conversational answer; `tools` are plain Python functions the model may call.

        The SDK runs the call loop (automatic function calling), capped at
        `max_tool_calls` so a confused model cannot spin on the quota.
        """
        types = self._types
        past = [
            types.Content(role="model" if turn["from"] == "neco" else "user", parts=[types.Part.from_text(text=turn["text"])])
            for turn in history
        ]
        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=list(tools),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(maximum_remote_calls=max_tool_calls),
            temperature=0.2,
            max_output_tokens=2048,
        )
        # A chat session is the SDK's recommended home for automatic function calling.
        session = self._client.chats.create(model=self.model, config=config, history=past)
        text = (self._guarded(lambda: session.send_message(question)).text or "").strip()
        if not text:
            raise ProviderUnavailable("empty answer")
        return text
