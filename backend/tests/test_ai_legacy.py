"""Baseline for the legacy prompt-stuffing /api/ai/chat endpoint (replaced in M6)."""
from types import SimpleNamespace

import routers.ai as ai_router


def test_ai_returns_503_without_key(client, monkeypatch):
    monkeypatch.setattr(ai_router, "OPENAI_API_KEY", "")
    res = client.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert res.status_code == 503


def test_ai_stuffs_filtered_listings_into_prompt(client, make_property, monkeypatch):
    make_property(title="Women-only room in Dhanmondi", is_female_only=True, price=7000)
    make_property(title="Big family flat in Mirpur", price=40000)
    captured = {}

    class FakeOpenAI:
        def __init__(self, api_key):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **kwargs):
            captured.update(kwargs)
            msg = SimpleNamespace(content="Try the Dhanmondi room.")
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    monkeypatch.setattr(ai_router, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(ai_router, "OpenAI", FakeOpenAI)
    res = client.post("/api/ai/chat", json={
        "messages": [{"role": "user", "content": "room for a girl"}],
        "budget_max": 10000, "is_female_only": True})
    assert res.status_code == 200
    assert res.json() == {"reply": "Try the Dhanmondi room."}
    system = captured["messages"][0]["content"]
    assert "Women-only room in Dhanmondi" in system
    assert "Mirpur" not in system
