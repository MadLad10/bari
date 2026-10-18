from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal

# Messages use the OpenAI chat format: {"role": ..., "content": ..., "tool_calls": [...], "tool_call_id": ...}
Message = dict


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON-encoded object, exactly as the model produced it


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    finish_reason: str | None = None

    def as_message(self) -> Message:
        msg: Message = {"role": "assistant", "content": self.content or ""}
        if self.tool_calls:
            msg["tool_calls"] = [
                {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": tc.arguments}}
                for tc in self.tool_calls
            ]
        return msg


@dataclass
class StreamChunk:
    kind: Literal["token", "done"]
    text: str = ""
    response: LLMResponse | None = None


class LLMError(Exception):
    """Provider failure. `retryable` marks transient errors (timeouts, 429, 5xx, connection)."""

    def __init__(self, message: str, *, retryable: bool = False, retry_after: float | None = None,
                 status: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after
        self.status = status


class LLMProvider(ABC):
    name: str = "base"
    model: str = ""

    @abstractmethod
    def chat(self, messages: list[Message], tools: list[dict] | None = None, *, temperature: float = 0.2,
             max_tokens: int = 800, json_mode: bool = False, timeout: float = 60) -> LLMResponse:
        """One completion. `tools` uses the OpenAI function-tool schema."""

    @abstractmethod
    def stream(self, messages: list[Message], tools: list[dict] | None = None, *, temperature: float = 0.2,
               max_tokens: int = 800, timeout: float = 60) -> Iterator[StreamChunk]:
        """Yield `token` chunks as text arrives, then exactly one `done` chunk carrying the full response."""
