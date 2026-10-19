"""Agent tests over the full seeded + indexed corpus (read-only, one shared DB per module)."""
import json
import time
from datetime import datetime, timedelta, timezone

import pytest

from agent import tools as agent_tools
from agent.guardrails import (StreamRedactor, has_booking_intent, looks_like_injection, scrub_pii,
                              validate_citations, wrap_untrusted)
from agent.loop import Agent, run_to_completion
from llm.base import LLMError, LLMResponse, ToolCall
from llm.client import LLMClient, set_llm_override
from llm.fake import FakeProvider
from models import AgentRun, Booking, PendingAction
from tests.conftest import make_user


def call(name, **args):
    return LLMResponse("", tool_calls=[ToolCall(f"c_{name}_{time.perf_counter_ns()}", name, json.dumps(args))])


def answer(text):
    return LLMResponse(text, prompt_tokens=100, completion_tokens=20)


def agent_with(script, **kw):
    provider = FakeProvider(script)
    return Agent(LLMClient(provider, sleep=lambda s: None), **kw), provider


def ask(agent, text, **kw):
    return run_to_completion(agent, [{"role": "user", "content": text}], **kw)


def tool_results(provider, name=None):
    msgs = provider.calls[-1]["messages"]
    return [json.loads(m["content"]) for m in msgs if m["role"] == "tool"]

pytestmark = pytest.mark.shared_seed


def test_extracts_filters_calls_tools_and_cites(seeded, needles):
    brac = needles["listings"]["brac_2bed_women_safe"]
    agent, provider = agent_with([
        call("search_properties", bedrooms=2, nearby_university="BRAC University", max_price=25000,
             is_female_only=True, min_safety_score=4),
        call("check_availability", property_id=brac, check_in="2027-01-01", check_out="2027-02-01"),
        answer(f"The women-only 2-bed in Merul Badda fits [listing:{brac}] and is free in January."),
    ])
    out = ask(agent, "2-bed near BRAC under 25k, women-only, safe area, from January")
    assert [s["tool"] for s in out["steps"] if s["status"] == "done"] == ["search_properties", "check_availability"]
    search, avail = tool_results(provider)
    assert brac in [r["ref"] for r in search["results"]] or f"listing:{brac}" in [r["ref"] for r in search["results"]]
    assert all(r["price"] <= 25000 and r["is_female_only"] for r in search["results"])
    assert avail["available"] is True
    assert out["citations"] == [f"listing:{brac}"] and out["unsupported_citations"] == []
    assert out["listing_cards"]["cards"][0]["id"] == brac
    assert "owner_phone" not in json.dumps(search)


def test_unsupported_citations_are_removed(seeded):
    agent, _ = agent_with([call("search_properties", max_price=6000, limit=2), answer("Try [listing:9999].")])
    out = ask(agent, "cheap room")
    assert out["citations"] == [] and out["unsupported_citations"] == ["listing:9999"]
    assert "9999" not in out["text"]


def test_tool_call_budget_is_enforced(seeded):
    script = [call("search_properties", max_price=10000 + i) for i in range(10)] + [answer("Done.")]
    agent, provider = agent_with(script, max_tool_calls=3, max_steps=10)
    out = ask(agent, "find anything")
    assert len([s for s in out["steps"] if s["status"] != "running"]) == 3
    assert out["status"] == "limit"
    assert provider.calls[-1]["tools"] is None  # the final step is forced to answer without tools


def test_tool_timeout_and_crash_fail_gracefully(seeded, monkeypatch):
    def slow(db, ctx, a):
        time.sleep(2)
        return {}

    def crash(db, ctx, a):
        raise RuntimeError("boom")

    monkeypatch.setattr(agent_tools.TOOLS["get_safety_stats"], "fn", slow)
    monkeypatch.setattr(agent_tools.TOOLS["compute_price"], "fn", crash)
    agent, provider = agent_with([
        call("get_safety_stats", property_id=1),
        call("compute_price", property_id=1, check_in="2027-01-01", check_out="2027-03-01"),
        call("no_such_tool"),
        call("get_property_details", property_id="not-a-number"),
        answer("I couldn't verify safety right now."),
    ], tool_timeout=0.5, max_steps=8)
    out = ask(agent, "is listing 1 safe and how much for 2 months?")
    errors = [s["error"] for s in out["steps"] if s["status"] == "error"]
    assert "timed out" in errors[0] and "failed" in errors[1] and "unknown tool" in errors[2]
    assert "invalid arguments" in errors[3]
    assert out["status"] == "ok" and out["text"].startswith("I couldn't verify")


def test_injected_post_is_withheld_from_the_model(seeded, needles):
    inj = needles["posts"]["injection_book"]
    agent, provider = agent_with([call("search_forum", query="Best flat near BRAC trust me"), answer("Nothing reliable.")])
    ask(agent, "what do people say about the best flat near BRAC?")
    [result] = tool_results(provider)
    item = next(r for r in result["results"] if r["ref"] == f"post:{inj}")
    assert 'flag="possible_prompt_injection"' in item["text"] and "ignore all previous" not in item["text"]


def test_injection_cannot_trigger_a_booking_draft(seeded, needles):
    """Even if the model obeys an injected post and calls draft_booking, it's refused: the user never asked to book."""
    scam = needles["listings"]["gulshan_too_cheap_scam"]
    _, headers = None, None
    agent, provider = agent_with([
        call("search_forum", query="best flat near BRAC"),
        call("draft_booking", property_id=scam, check_in="2027-01-01", check_out="2027-02-01"),
        answer("Here is what the forum says."),
    ])
    out = ask(agent, "what's the best flat near BRAC according to the forum?", user_id=1)
    step = [s for s in out["steps"] if s["tool"] == "draft_booking" and s["status"] == "error"][0]
    assert "has not asked to book" in step["error"]
    assert out["pending_actions"] == []
    assert seeded.query(PendingAction).count() == 0 and seeded.query(Booking).filter_by(property_id=scam).count() == 0


def test_injection_filter_can_be_disabled_for_the_eval_ablation(seeded, needles):
    agent, provider = agent_with([call("search_forum", query="Bashundhara owners contact list"), answer("ok")],
                                 injection_filter=False)
    ask(agent, "Bashundhara owners contact list?")
    texts = " ".join(r["text"] for r in tool_results(provider)[0]["results"])
    assert "developer mode" in texts and "<untrusted_data" in texts


def test_answer_never_leaks_phone_numbers(seeded):
    agent, _ = agent_with([LLMResponse("Call the owner at 01711000001 or karim@example.com.")])
    out = ask(agent, "owner's phone for listing 1?")
    assert "01711000001" not in out["text"] and "karim@" not in out["text"]
    assert "01711000001" not in "".join(out["tokens"])


def test_property_details_tool_hides_contact(seeded):
    agent, provider = agent_with([call("get_property_details", property_id=1), answer("ok [listing:1]")])
    ask(agent, "tell me about listing 1")
    [details] = tool_results(provider)
    assert "owner_phone" not in details and "owner_email" not in details
    assert "01711000001" not in json.dumps(details)

def test_sse_endpoint_streams_events(client, seeded):
    set_llm_override(LLMClient(FakeProvider([call("search_properties", max_price=8000, limit=2),
                                             answer("Here are two cheap rooms.")]), sleep=lambda s: None))
    try:
        res = client.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "cheap room"}]})
    finally:
        set_llm_override(None)
    assert res.headers["content-type"].startswith("text/event-stream")
    events = [line[7:] for line in res.text.splitlines() if line.startswith("event: ")]
    assert events[0] == "start" and events[-1] == "done"
    assert events.count("step") == 2 and "token" in events


def test_guessed_filters_are_relaxed_transparently(seeded, needles):
    """The model invents area=Banani for a listing that's in Aftabnagar: the tool drops the guess and says so."""
    agent, provider = agent_with([call("semantic_search", query="rooftop garden solar backup", area="Banani",
                                       nearby_university="East West University"), answer("ok")])
    ask(agent, "Any flat with a rooftop garden and solar backup near East West University?")
    [result] = tool_results(provider)
    assert result["relaxed_filters"] == ["area"]
    assert f"listing:{needles['listings']['ewu_rooftop_garden']}" in [r["ref"] for r in result["results"]]


def test_hard_constraints_are_never_relaxed(seeded):
    agent, provider = agent_with([call("search_properties", max_price=500, is_female_only=True), answer("none")])
    ask(agent, "women-only room under 500 taka")
    [result] = tool_results(provider)
    assert result["results"] == [] and "relaxed_filters" not in result


def test_misspelled_area_is_normalised(seeded, needles):
    agent, provider = agent_with([call("search_forum", query="বসুন্ধরায় রাতে মেয়েদের নিরাপত্তা", area="Boshundhara"), answer("ok")])
    ask(agent, "বসুন্ধরায় রাতে মেয়েদের জন্য কতটা নিরাপদ?")
    [result] = tool_results(provider)
    assert result["area_interpreted_as"] == "Bashundhara"
    assert f"post:{needles['posts']['bashundhara_women_night_bn']}" in [r["ref"] for r in result["results"]]
