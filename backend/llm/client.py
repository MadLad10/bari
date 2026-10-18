"""LLMClient: retries with backoff, per-attempt timeouts, and a row in `llm_calls` for every call."""
from __future__ import annotations

import logging
import random
import time
import uuid
from collections.abc import Callable, Iterator
from functools import lru_cache

from config import settings
from llm.base import LLMError, LLMProvider, LLMResponse, Message, StreamChunk
from llm.context import request_id_var
from llm.pricing import estimate_cost

log = logging.getLogger("bari.llm")


def backoff_delay(attempt: int, error: LLMError, base: float, cap: float) -> float:
    """Exponential backoff with full jitter; honours Retry-After when the provider sends it."""
    if error.retry_after is not None:
        return min(error.retry_after, cap * 4)
    return random.uniform(0, min(cap, base * 2 ** attempt))


def record_call(**row) -> None:
    """Insert one llm_calls row in its own session. Never raises: logging must not break a request."""
    from database import SessionLocal
    from models import LLMCall

    db = SessionLocal()
    try:
        db.add(LLMCall(**row))
        db.commit()
    except Exception as e:  # noqa: BLE001
        log.warning("failed to log LLM call: %s", e)
        db.rollback()
    finally:
        db.close()


class LLMClient:
    def __init__(self, provider: LLMProvider, *, max_retries: int | None = None, timeout: float | None = None,
                 base_delay: float = 0.5, max_delay: float = 8.0, sleep: Callable[[float], None] = time.sleep):
        self.provider = provider
        self.max_retries = settings.llm_max_retries if max_retries is None else max_retries
        self.timeout = settings.llm_timeout_s if timeout is None else timeout
        self.base_delay, self.max_delay, self._sleep = base_delay, max_delay, sleep

    @property
    def name(self) -> str:
        return self.provider.name

    @property
    def model(self) -> str:
        return self.provider.model

    def _log(self, *, purpose: str, request_id: str | None, started: float, attempts: int,
             response: LLMResponse | None = None, error: Exception | None = None) -> None:
        p = response.prompt_tokens if response else 0
        c = response.completion_tokens if response else 0
        model = (response.model if response and response.model else None) or self.provider.model
        record_call(
            request_id=request_id or request_id_var.get() or uuid.uuid4().hex,
            provider=self.provider.name, model=model, purpose=purpose,
            prompt_tokens=p, completion_tokens=c,
            latency_ms=int((time.perf_counter() - started) * 1000),
            cost_usd=estimate_cost(self.provider.name, model, p, c),
            status="ok" if error is None else "error",
            error=None if error is None else str(error)[:1000],
            attempts=attempts,
        )

    def chat(self, messages: list[Message], tools: list[dict] | None = None, *, purpose: str = "chat",
             request_id: str | None = None, **kw) -> LLMResponse:
        started = time.perf_counter()
        attempt = 0
        while True:
            try:
                resp = self.provider.chat(messages, tools, timeout=self.timeout, **kw)
                self._log(purpose=purpose, request_id=request_id, started=started, attempts=attempt + 1, response=resp)
                return resp
            except LLMError as e:
                if not e.retryable or attempt >= self.max_retries:
                    self._log(purpose=purpose, request_id=request_id, started=started, attempts=attempt + 1, error=e)
                    raise
                delay = backoff_delay(attempt, e, self.base_delay, self.max_delay)
                log.info("LLM %s retry %d in %.1fs: %s", self.provider.name, attempt + 1, delay, e)
                self._sleep(delay)
                attempt += 1

    def stream(self, messages: list[Message], tools: list[dict] | None = None, *, purpose: str = "chat",
               request_id: str | None = None, **kw) -> Iterator[StreamChunk]:
        """Stream tokens. Retries only happen before the first chunk; once text reaches the user, failures surface."""
        started = time.perf_counter()
        attempt = 0
        while True:
            emitted = False
            try:
                for chunk in self.provider.stream(messages, tools, timeout=self.timeout, **kw):
                    if chunk.kind == "done":
                        self._log(purpose=purpose, request_id=request_id, started=started,
                                  attempts=attempt + 1, response=chunk.response)
                    emitted = True
                    yield chunk
                return
            except LLMError as e:
                if emitted or not e.retryable or attempt >= self.max_retries:
                    self._log(purpose=purpose, request_id=request_id, started=started, attempts=attempt + 1, error=e)
                    raise
                self._sleep(backoff_delay(attempt, e, self.base_delay, self.max_delay))
                attempt += 1


_override: dict[str, LLMClient] = {}


def set_llm_override(client: LLMClient | None, provider: str | None = None) -> None:
    """Tests and the eval runner can swap in a client (e.g. wrapping FakeProvider)."""
    key = provider or "default"
    if client is None:
        _override.pop(key, None)
    else:
        _override[key] = client


@lru_cache
def _build(provider: str) -> LLMClient:
    if provider == "api":
        from llm.openai_compat import OpenAICompatProvider
        return LLMClient(OpenAICompatProvider(settings.llm_api_base_url, settings.llm_api_key, settings.llm_api_model))
    if provider == "ollama":
        from llm.ollama import OllamaProvider
        return LLMClient(OllamaProvider(settings.ollama_base_url, settings.ollama_model, settings.ollama_num_ctx),
                         timeout=settings.ollama_timeout_s)
    if provider == "fake":
        from llm.fake import FakeProvider
        return LLMClient(FakeProvider())
    raise ValueError(f"unknown LLM provider {provider!r} (expected api | ollama | fake)")


def get_llm(provider: str | None = None) -> LLMClient:
    """The configured client (LLM_PROVIDER), or a specific one: get_llm("ollama")."""
    if provider in _override:
        return _override[provider]
    if provider is None and "default" in _override:
        return _override["default"]
    return _build(provider or settings.llm_provider)
