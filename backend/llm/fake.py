"""Scripted provider for tests: no network, deterministic."""
from __future__ import annotations

from collections.abc import Callable, Iterator

from llm.base import LLMError, LLMProvider, LLMResponse, Message, StreamChunk

Step = LLMResponse | LLMError | Callable[[list[Message], list[dict] | None], LLMResponse]


class FakeProvider(LLMProvider):
    name = "fake"

    def __init__(self, script: list[Step] | None = None, model: str = "fake-model"):
        self.model = model
        self.script = list(script or [])
        self.calls: list[dict] = []

    def _next(self, messages, tools) -> LLMResponse:
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools})
        if not self.script:
            return LLMResponse(content="(fake: script exhausted)", model=self.model,
                               prompt_tokens=10, completion_tokens=5)
        step = self.script.pop(0)
        if isinstance(step, LLMError):
            raise step
        resp = step(messages, tools) if callable(step) else step
        resp.model = resp.model or self.model
        return resp

    def chat(self, messages, tools=None, **_) -> LLMResponse:
        return self._next(messages, tools)

    def stream(self, messages, tools=None, **_) -> Iterator[StreamChunk]:
        resp = self._next(messages, tools)
        for word in (resp.content or "").split(" "):
            if word:
                yield StreamChunk("token", word + " ")
        yield StreamChunk("done", response=resp)
