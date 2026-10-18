"""Local models through Ollama's native /api/chat endpoint.

The native API is used instead of Ollama's OpenAI-compatible /v1 endpoint because only the native
API lets us set `num_ctx`. The default context window is small, and Ollama silently truncates
prompts that overflow it, which drops the system prompt and the tool results.
"""
from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

from llm.base import LLMError, LLMProvider, LLMResponse, Message, StreamChunk, ToolCall


def to_ollama_messages(messages: list[Message]) -> list[dict]:
    out = []
    names_by_id: dict[str, str] = {}
    for m in messages:
        if m["role"] == "assistant" and m.get("tool_calls"):
            calls = []
            for tc in m["tool_calls"]:
                names_by_id[tc["id"]] = tc["function"]["name"]
                args = tc["function"]["arguments"]
                calls.append({"function": {"name": tc["function"]["name"],
                                           "arguments": json.loads(args) if isinstance(args, str) and args else (args or {})}})
            out.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": calls})
        elif m["role"] == "tool":
            out.append({"role": "tool", "content": m["content"],
                        "tool_name": names_by_id.get(m.get("tool_call_id", ""), "")})
        else:
            out.append({"role": m["role"], "content": m.get("content") or ""})
    return out


def _tool_calls(msg: dict, offset: int = 0) -> list[ToolCall]:
    calls = []
    for i, tc in enumerate(msg.get("tool_calls") or []):
        fn = tc.get("function", {})
        args = fn.get("arguments", {})
        calls.append(ToolCall(id=f"call_{offset + i}", name=fn.get("name", ""),
                              arguments=args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)))
    return calls


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, base_url: str, model: str, num_ctx: int = 16384, keep_alive: str = "10m",
                 transport: httpx.BaseTransport | None = None):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.num_ctx = num_ctx
        self.keep_alive = keep_alive
        self._transport = transport

    def _body(self, messages, tools, temperature, max_tokens, stream, json_mode=False) -> dict:
        body = {"model": self.model, "messages": to_ollama_messages(messages), "stream": stream,
                "keep_alive": self.keep_alive,
                "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": self.num_ctx}}
        if tools:
            body["tools"] = tools
        if json_mode:
            body["format"] = "json"
        return body

    def _client(self, timeout: float) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, timeout=timeout, transport=self._transport)

    @staticmethod
    def _raise_for(e: Exception) -> LLMError:
        if isinstance(e, httpx.TimeoutException):
            return LLMError(f"ollama timeout: {e}", retryable=True)
        if isinstance(e, httpx.TransportError):
            return LLMError(f"ollama unreachable: {e}", retryable=True)
        if isinstance(e, httpx.HTTPStatusError):
            code = e.response.status_code
            try:
                detail = e.response.json().get("error", e.response.text)
            except Exception:  # noqa: BLE001
                detail = e.response.text
            return LLMError(f"ollama HTTP {code}: {detail}", retryable=code >= 500, status=code)
        return LLMError(str(e))

    def chat(self, messages, tools=None, *, temperature=0.2, max_tokens=800, json_mode=False,
             timeout=60) -> LLMResponse:
        try:
            with self._client(timeout) as c:
                r = c.post("/api/chat", json=self._body(messages, tools, temperature, max_tokens, False, json_mode))
                r.raise_for_status()
                data = r.json()
        except Exception as e:  # noqa: BLE001
            raise self._raise_for(e) from e
        msg = data.get("message", {})
        return LLMResponse(content=msg.get("content", ""), tool_calls=_tool_calls(msg),
                           prompt_tokens=data.get("prompt_eval_count", 0),
                           completion_tokens=data.get("eval_count", 0),
                           model=data.get("model", self.model), finish_reason=data.get("done_reason"))

    def stream(self, messages, tools=None, *, temperature=0.2, max_tokens=800, timeout=60) -> Iterator[StreamChunk]:
        content, calls, final = [], [], {}
        try:
            with self._client(timeout) as c, c.stream(
                "POST", "/api/chat", json=self._body(messages, tools, temperature, max_tokens, True)
            ) as r:
                if r.status_code >= 400:
                    r.read()
                    r.raise_for_status()
                for line in r.iter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if data.get("error"):
                        raise LLMError(f"ollama: {data['error']}")
                    msg = data.get("message", {})
                    if msg.get("content"):
                        content.append(msg["content"])
                        yield StreamChunk("token", msg["content"])
                    calls += _tool_calls(msg, offset=len(calls))
                    if data.get("done"):
                        final = data
        except LLMError:
            raise
        except Exception as e:  # noqa: BLE001
            raise self._raise_for(e) from e
        yield StreamChunk("done", response=LLMResponse(
            content="".join(content), tool_calls=calls,
            prompt_tokens=final.get("prompt_eval_count", 0), completion_tokens=final.get("eval_count", 0),
            model=final.get("model", self.model), finish_reason=final.get("done_reason"),
        ))

    def embed(self, texts: list[str], model: str, timeout: float = 120) -> tuple[list[list[float]], int]:
        """Returns (embeddings, prompt token count)."""
        try:
            with self._client(timeout) as c:
                r = c.post("/api/embed", json={"model": model, "input": texts, "keep_alive": self.keep_alive})
                r.raise_for_status()
                data = r.json()
                return data["embeddings"], data.get("prompt_eval_count", 0)
        except Exception as e:  # noqa: BLE001
            raise self._raise_for(e) from e
