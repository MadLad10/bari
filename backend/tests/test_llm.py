import json

import httpx
import pytest

from llm.base import LLMError, LLMResponse, ToolCall
from llm.client import LLMClient, backoff_delay
from llm.context import request_id_var
from llm.fake import FakeProvider
from llm.ollama import OllamaProvider, to_ollama_messages
from llm.openai_compat import OpenAICompatProvider
from llm.pricing import estimate_cost
from models import LLMCall

MSGS = [{"role": "user", "content": "hi"}]


def _client(provider, **kw):
    sleeps = []
    c = LLMClient(provider, max_retries=kw.pop("max_retries", 3), timeout=5, sleep=sleeps.append, **kw)
    return c, sleeps


def _rows(db):
    db.expire_all()
    return db.query(LLMCall).order_by(LLMCall.id).all()


def test_success_is_logged_with_tokens_cost_and_request_id(db):
    provider = FakeProvider([LLMResponse("hello", prompt_tokens=1000, completion_tokens=500)],
                            model="llama-3.3-70b-versatile")
    provider.name = "api"
    client, _ = _client(provider)
    token = request_id_var.set("req-123")
    try:
        assert client.chat(MSGS, purpose="test").content == "hello"
    finally:
        request_id_var.reset(token)
    [row] = _rows(db)
    assert (row.request_id, row.provider, row.model, row.purpose) == ("req-123", "api", "llama-3.3-70b-versatile", "test")
    assert (row.prompt_tokens, row.completion_tokens, row.status, row.attempts) == (1000, 500, "ok", 1)
    assert row.cost_usd == pytest.approx((1000 * 0.59 + 500 * 0.79) / 1e6)
    assert row.latency_ms >= 0


def test_retries_transient_errors_with_backoff(db):
    provider = FakeProvider([LLMError("timeout", retryable=True), LLMError("HTTP 503", retryable=True),
                             LLMResponse("ok")])
    client, sleeps = _client(provider)
    assert client.chat(MSGS).content == "ok"
    assert len(sleeps) == 2
    [row] = _rows(db)
    assert row.attempts == 3 and row.status == "ok"


def test_non_retryable_error_fails_fast_and_is_logged(db):
    client, sleeps = _client(FakeProvider([LLMError("HTTP 401: bad key", retryable=False, status=401)]))
    with pytest.raises(LLMError, match="401"):
        client.chat(MSGS)
    assert sleeps == []
    [row] = _rows(db)
    assert row.status == "error" and "401" in row.error


def test_gives_up_after_max_retries(db):
    client, sleeps = _client(FakeProvider([LLMError("timeout", retryable=True)] * 5), max_retries=2)
    with pytest.raises(LLMError):
        client.chat(MSGS)
    assert len(sleeps) == 2
    assert _rows(db)[0].attempts == 3


def test_backoff_honours_retry_after_and_caps():
    assert backoff_delay(0, LLMError("429", retryable=True, retry_after=7), 0.5, 8) == 7
    for attempt in range(10):
        assert 0 <= backoff_delay(attempt, LLMError("x", retryable=True), 0.5, 8) <= 8


def test_stream_retries_only_before_first_token(db):
    provider = FakeProvider([LLMError("conn reset", retryable=True), LLMResponse("one two three")])
    client, sleeps = _client(provider)
    chunks = list(client.stream(MSGS))
    assert "".join(c.text for c in chunks if c.kind == "token").split() == ["one", "two", "three"]
    assert chunks[-1].kind == "done" and len(sleeps) == 1
    assert _rows(db)[0].attempts == 2


def test_cost_estimates():
    assert estimate_cost("api", "gpt-4o-mini", 1_000_000, 1_000_000) == pytest.approx(0.75)
    assert estimate_cost("ollama", "qwen2.5:7b-instruct", 10_000, 10_000) == 0
    assert estimate_cost("api", "unknown-model", 10, 10) == 0


def test_request_id_header(client):
    assert client.get("/api/health", headers={"X-Request-ID": "abc"}).headers["x-request-id"] == "abc"
    assert len(client.get("/api/health").headers["x-request-id"]) == 32


# ── OpenAI-compatible provider (Groq) over a mocked HTTP transport ────────────

def _openai(handler):
    return OpenAICompatProvider("https://api.groq.test/openai/v1", "test-key", "llama-3.3-70b-versatile",
                                http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_openai_compat_parses_tool_calls():
    def handler(req):
        body = json.loads(req.content)
        assert body["tools"][0]["function"]["name"] == "search_properties"
        assert req.headers["authorization"] == "Bearer test-key"
        return httpx.Response(200, json={
            "id": "x", "object": "chat.completion", "created": 0, "model": "llama-3.3-70b-versatile",
            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": None,
                "tool_calls": [{"id": "call_1", "type": "function",
                                "function": {"name": "search_properties", "arguments": "{\"max_price\": 25000}"}}]}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}})

    tools = [{"type": "function", "function": {"name": "search_properties", "parameters": {"type": "object"}}}]
    r = _openai(handler).chat(MSGS, tools)
    assert r.tool_calls == [ToolCall("call_1", "search_properties", '{"max_price": 25000}')]
    assert (r.prompt_tokens, r.completion_tokens, r.finish_reason) == (120, 30, "tool_calls")


def test_openai_compat_stream_assembles_tool_call_deltas():
    def sse(obj):
        return f"data: {json.dumps(obj)}\n\n"

    base = {"id": "x", "object": "chat.completion.chunk", "created": 0, "model": "m"}
    events = [
        {**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": "Let me "}}]},
        {**base, "choices": [{"index": 0, "delta": {"content": "check."}}]},
        {**base, "choices": [{"index": 0, "delta": {"tool_calls": [
            {"index": 0, "id": "call_9", "type": "function", "function": {"name": "get_safety", "arguments": ""}}]}}]},
        {**base, "choices": [{"index": 0, "delta": {"tool_calls": [
            {"index": 0, "function": {"arguments": "{\"property_id\""}}]}}]},
        {**base, "choices": [{"index": 0, "delta": {"tool_calls": [
            {"index": 0, "function": {"arguments": ": 11}"}}]}, "finish_reason": "tool_calls"}]},
        {**base, "choices": [], "usage": {"prompt_tokens": 50, "completion_tokens": 12, "total_tokens": 62}},
    ]
    body = "".join(sse(e) for e in events) + "data: [DONE]\n\n"
    p = _openai(lambda req: httpx.Response(200, text=body, headers={"content-type": "text/event-stream"}))
    chunks = list(p.stream(MSGS))
    assert "".join(c.text for c in chunks if c.kind == "token") == "Let me check."
    done = chunks[-1].response
    assert done.tool_calls == [ToolCall("call_9", "get_safety", '{"property_id": 11}')]
    assert (done.prompt_tokens, done.completion_tokens) == (50, 12)


def test_openai_compat_maps_rate_limit_to_retryable():
    p = _openai(lambda req: httpx.Response(429, json={"error": {"message": "slow down"}}, headers={"retry-after": "3"}))
    with pytest.raises(LLMError) as e:
        p.chat(MSGS)
    assert e.value.retryable and e.value.retry_after == 3 and e.value.status == 429


def test_openai_compat_requires_key():
    with pytest.raises(LLMError, match="LLM_API_KEY"):
        OpenAICompatProvider("https://x", "", "m")


# ── Ollama native provider ────────────────────────────────────────────────────

def test_ollama_chat_sets_context_and_parses_tool_calls():
    def handler(req):
        body = json.loads(req.content)
        assert body["options"]["num_ctx"] == 16384 and body["stream"] is False
        return httpx.Response(200, json={
            "model": "qwen2.5:7b-instruct", "done": True, "done_reason": "stop",
            "message": {"role": "assistant", "content": "",
                        "tool_calls": [{"function": {"name": "semantic_search", "arguments": {"query": "নিরাপদ"}}}]},
            "prompt_eval_count": 300, "eval_count": 20})

    p = OllamaProvider("http://ollama:11434", "qwen2.5:7b-instruct", transport=httpx.MockTransport(handler))
    r = p.chat(MSGS, [{"type": "function", "function": {"name": "semantic_search"}}])
    assert r.tool_calls[0].name == "semantic_search"
    assert json.loads(r.tool_calls[0].arguments) == {"query": "নিরাপদ"}
    assert (r.prompt_tokens, r.completion_tokens) == (300, 20)


def test_ollama_stream_and_errors():
    lines = [{"message": {"content": "Hel"}, "done": False}, {"message": {"content": "lo"}, "done": False},
             {"message": {"content": ""}, "done": True, "prompt_eval_count": 9, "eval_count": 2, "model": "q"}]
    body = "\n".join(json.dumps(l) for l in lines)
    p = OllamaProvider("http://o", "q", transport=httpx.MockTransport(lambda r: httpx.Response(200, text=body)))
    chunks = list(p.stream(MSGS))
    assert chunks[-1].response.content == "Hello" and chunks[-1].response.completion_tokens == 2

    missing = OllamaProvider("http://o", "nope", transport=httpx.MockTransport(
        lambda r: httpx.Response(404, json={"error": "model 'nope' not found"})))
    with pytest.raises(LLMError) as e:
        missing.chat(MSGS)
    assert not e.value.retryable and "not found" in str(e.value)

    def boom(req):
        raise httpx.ConnectError("refused")
    with pytest.raises(LLMError) as e:
        OllamaProvider("http://o", "q", transport=httpx.MockTransport(boom)).chat(MSGS)
    assert e.value.retryable


def test_ollama_message_conversion_keeps_tool_names():
    msgs = [{"role": "assistant", "content": "", "tool_calls": [
        {"id": "call_0", "type": "function", "function": {"name": "get_safety_stats", "arguments": "{\"property_id\": 3}"}}]},
        {"role": "tool", "tool_call_id": "call_0", "content": "{\"avg\": 4}"}]
    out = to_ollama_messages(msgs)
    assert out[0]["tool_calls"][0]["function"]["arguments"] == {"property_id": 3}
    assert out[1] == {"role": "tool", "content": "{\"avg\": 4}", "tool_name": "get_safety_stats"}
