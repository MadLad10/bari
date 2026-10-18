"""Any OpenAI-compatible chat API: Groq (default), OpenAI, OpenRouter, vLLM…"""
from __future__ import annotations

import json
from collections.abc import Iterator

import httpx
import openai

from llm.base import LLMError, LLMProvider, LLMResponse, Message, StreamChunk, ToolCall


def _map_error(e: Exception) -> LLMError:
    if isinstance(e, openai.APITimeoutError):
        return LLMError(f"timeout: {e}", retryable=True)
    if isinstance(e, openai.APIConnectionError):
        return LLMError(f"connection error: {e}", retryable=True)
    if isinstance(e, openai.APIStatusError):
        retry_after = None
        try:
            retry_after = float(e.response.headers.get("retry-after", ""))
        except (TypeError, ValueError):
            pass
        retryable = e.status_code == 429 or e.status_code >= 500
        return LLMError(f"HTTP {e.status_code}: {e.message}", retryable=retryable, retry_after=retry_after,
                        status=e.status_code)
    return LLMError(str(e))


class OpenAICompatProvider(LLMProvider):
    name = "api"

    def __init__(self, base_url: str, api_key: str, model: str, http_client: httpx.Client | None = None):
        if not api_key:
            raise LLMError("LLM_API_KEY is not set. Add your Groq (or OpenAI) key to .env", retryable=False)
        self.model = model
        # Retries are handled by LLMClient, so the SDK's own retry loop is disabled.
        self._client = openai.OpenAI(base_url=base_url, api_key=api_key, max_retries=0, http_client=http_client)

    def _kwargs(self, messages, tools, temperature, max_tokens, timeout) -> dict:
        kw = {"model": self.model, "messages": messages, "temperature": temperature,
              "max_tokens": max_tokens, "timeout": timeout}
        if tools:
            kw["tools"] = tools
            kw["tool_choice"] = "auto"
        return kw

    def chat(self, messages: list[Message], tools=None, *, temperature=0.2, max_tokens=800,
             json_mode=False, timeout=60) -> LLMResponse:
        kw = self._kwargs(messages, tools, temperature, max_tokens, timeout)
        if json_mode:
            kw["response_format"] = {"type": "json_object"}
        try:
            r = self._client.chat.completions.create(**kw)
        except Exception as e:  # noqa: BLE001
            raise _map_error(e) from e
        choice = r.choices[0]
        calls = [ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments or "{}")
                 for tc in (choice.message.tool_calls or [])]
        return LLMResponse(
            content=choice.message.content or "", tool_calls=calls,
            prompt_tokens=r.usage.prompt_tokens if r.usage else 0,
            completion_tokens=r.usage.completion_tokens if r.usage else 0,
            model=r.model or self.model, finish_reason=choice.finish_reason,
        )

    def stream(self, messages: list[Message], tools=None, *, temperature=0.2, max_tokens=800,
               timeout=60) -> Iterator[StreamChunk]:
        kw = self._kwargs(messages, tools, temperature, max_tokens, timeout)
        try:
            events = self._client.chat.completions.create(**kw, stream=True, stream_options={"include_usage": True})
            content, calls, usage, finish, model = [], {}, None, None, self.model
            for ev in events:
                usage = ev.usage or usage
                model = ev.model or model
                if not ev.choices:
                    continue
                delta = ev.choices[0].delta
                finish = ev.choices[0].finish_reason or finish
                if delta.content:
                    content.append(delta.content)
                    yield StreamChunk("token", delta.content)
                for tc in delta.tool_calls or []:
                    slot = calls.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                    slot["id"] = tc.id or slot["id"]
                    if tc.function:
                        slot["name"] += tc.function.name or ""
                        slot["arguments"] += tc.function.arguments or ""
        except LLMError:
            raise
        except Exception as e:  # noqa: BLE001
            raise _map_error(e) from e
        tool_calls = [ToolCall(id=c["id"] or f"call_{i}", name=c["name"], arguments=c["arguments"] or "{}")
                      for i, c in sorted(calls.items())]
        yield StreamChunk("done", response=LLMResponse(
            content="".join(content), tool_calls=tool_calls,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            model=model, finish_reason=finish,
        ))


def parse_arguments(raw: str) -> dict:
    """Tool-call arguments as a dict; tolerant of empty strings."""
    if not raw or not raw.strip():
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("tool arguments must be a JSON object")
    return value
