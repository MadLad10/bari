"""The agent loop: LLM ⇄ tools until the model answers, with hard limits, timeouts, guardrails and
grounded citations. Emits events that the HTTP layer turns into SSE."""
from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass

from agent.guardrails import (StreamRedactor, check_constraints, claims_no_evidence, extract_refs, parse_hard_constraints,
                              repair_citations, scrub_pii, validate_citations)
from agent.prompts import system_prompt
from agent.tools import TOOLS, ToolContext, ToolError, tool_schemas
from config import settings
from database import SessionLocal
from llm.base import LLMError
from llm.client import LLMClient
from llm.openai_compat import parse_arguments
from llm.pricing import estimate_cost
from models import AgentRun
from services import properties as property_svc

log = logging.getLogger("bari.agent")
_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="agent-tool")
MAX_HISTORY = 12


@dataclass
class AgentEvent:
    type: str
    data: dict


def _history(messages: list[dict]) -> list[dict]:
    clean = [{"role": m["role"], "content": str(m.get("content", ""))[:4000]}
             for m in messages if m.get("role") in ("user", "assistant") and m.get("content")]
    return clean[-MAX_HISTORY:]


def _execute(tool_name: str, raw_args: str, ctx: ToolContext) -> dict:
    """Run one tool in its own DB session. Errors become results the model can read."""
    tool = TOOLS.get(tool_name)
    if tool is None:
        raise ToolError(f"unknown tool {tool_name!r}")
    try:
        args = tool.parse(parse_arguments(raw_args))
    except (ValueError, json.JSONDecodeError) as e:
        raise ToolError(f"arguments are not valid JSON: {e}") from e
    db = SessionLocal()
    try:
        return tool.fn(db, ctx, args)
    finally:
        db.close()


class Agent:
    def __init__(self, llm: LLMClient, *, max_tool_calls: int | None = None, max_steps: int | None = None,
                 tool_timeout: float | None = None, turn_timeout: float | None = None,
                 injection_filter: bool | None = None):
        self.llm = llm
        self.max_tool_calls = max_tool_calls or settings.agent_max_tool_calls
        self.max_steps = max_steps or settings.agent_max_llm_steps
        self.tool_timeout = tool_timeout or settings.agent_tool_timeout_s
        self.turn_timeout = turn_timeout or settings.agent_turn_timeout_s
        self.injection_filter = settings.agent_injection_filter if injection_filter is None else injection_filter

    def run(self, messages: list[dict], *, user_id: int | None = None, request_id: str | None = None) -> Iterator[AgentEvent]:
        request_id = request_id or uuid.uuid4().hex
        started = time.perf_counter()
        history = _history(messages)
        question = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
        ctx = ToolContext(user_id=user_id, request_id=request_id, last_user_message=question,
                          injection_filter=self.injection_filter)
        # Refs the assistant already cited earlier in this conversation stay citable in follow-ups.
        for m in history:
            if m["role"] == "assistant":
                for ref in extract_refs(m["content"]):
                    ctx.cite(ref, carried=True)

        convo = [{"role": "system", "content": system_prompt()}, *history]
        trace: list[dict] = []
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        tool_calls_used, steps, status, error, final = 0, 0, "ok", None, ""
        nudged = False
        yield AgentEvent("start", {"request_id": request_id, "provider": self.llm.name, "model": self.llm.model})

        try:
            while True:
                steps += 1
                tools_allowed = tool_calls_used < self.max_tool_calls and steps < self.max_steps
                if not tools_allowed:
                    status = "limit"
                    convo.append({"role": "system", "content": "Tool limit reached. Answer now with the evidence "
                                  "you already have, and say what you could not verify."})
                if time.perf_counter() - started > self.turn_timeout:
                    raise TimeoutError(f"turn exceeded {self.turn_timeout:.0f}s")

                redactor = StreamRedactor()
                resp = None
                try:
                    for chunk in self.llm.stream(convo, tool_schemas() if tools_allowed else None, purpose="agent",
                                                 request_id=request_id, temperature=0.1, max_tokens=900):
                        if chunk.kind == "token":
                            if text := redactor.feed(chunk.text):
                                yield AgentEvent("token", {"text": text, "step": steps})
                        else:
                            resp = chunk.response
                except LLMError as e:
                    if tools_allowed:
                        raise
                    # Some models still try to call a tool when none are offered (Groq then rejects the turn).
                    # Retry once with an explicit instruction, then fall back to a summary of the evidence.
                    resp = self._forced_answer(convo, request_id, ctx, e)
                if tail := redactor.flush():
                    yield AgentEvent("token", {"text": tail, "step": steps})
                usage["prompt_tokens"] += resp.prompt_tokens
                usage["completion_tokens"] += resp.completion_tokens

                if not (resp.tool_calls and tools_allowed):
                    # Grounding guard: "bari has no information" is only allowed after actually searching.
                    if tool_calls_used == 0 and tools_allowed and not nudged and claims_no_evidence(resp.content):
                        nudged = True
                        convo += [{"role": "assistant", "content": resp.content},
                                  {"role": "system", "content": "You answered without searching. bari's listings, "
                                   "forum and safety reviews may well contain the answer: call the right search "
                                   "tool first, then answer from what it returns."}]
                        yield AgentEvent("reset", {"step": steps, "reason": "searching before answering"})
                        continue
                    final = resp.content
                    break

                convo.append(resp.as_message())
                for tc in resp.tool_calls:
                    if tool_calls_used >= self.max_tool_calls:
                        result, ok = {"error": "tool call limit reached; this call was not executed"}, False
                    else:
                        tool_calls_used += 1
                        tool = TOOLS.get(tc.name)
                        label = tc.name
                        try:
                            label = tool.label(tool.parse(parse_arguments(tc.arguments))) if tool else tc.name
                        except Exception:  # noqa: BLE001
                            pass
                        yield AgentEvent("step", {"id": tc.id, "tool": tc.name, "label": label, "status": "running"})
                        t0 = time.perf_counter()
                        try:
                            result = _POOL.submit(_execute, tc.name, tc.arguments, ctx).result(timeout=self.tool_timeout)
                            ok = True
                        except FutureTimeout:
                            result, ok = {"error": f"{tc.name} timed out after {self.tool_timeout:.0f}s"}, False
                        except ToolError as e:
                            result, ok = {"error": str(e)}, False
                        except Exception as e:  # noqa: BLE001
                            log.exception("tool %s crashed", tc.name)
                            result, ok = {"error": f"{tc.name} failed: {type(e).__name__}"}, False
                        ms = int((time.perf_counter() - t0) * 1000)
                        yield AgentEvent("step", {"id": tc.id, "tool": tc.name, "label": label,
                                                  "status": "done" if ok else "error", "ms": ms,
                                                  "error": result.get("error") if not ok else None})
                        if ok and tc.name == "draft_booking":
                            yield AgentEvent("pending_action", ctx.pending_actions[-1])
                    trace.append({"tool": tc.name, "arguments": tc.arguments, "ok": ok,
                                  "error": result.get("error") if not ok else None})
                    convo.append({"role": "tool", "tool_call_id": tc.id,
                                  "content": json.dumps(result, ensure_ascii=False, default=str)})
        except (LLMError, TimeoutError) as e:
            status, error = "error", str(e)
            yield AgentEvent("error", {"message": "The assistant is unavailable right now. Please try again.",
                                       "detail": str(e)[:300]})
        except Exception as e:  # noqa: BLE001
            log.exception("agent crashed")
            status, error = "error", f"{type(e).__name__}: {e}"
            yield AgentEvent("error", {"message": "Something went wrong. Please try again.", "detail": error[:300]})

        text, _ = scrub_pii(final or "")
        text, cited, unsupported = validate_citations(text, set(ctx.evidence))
        text, auto_cited = repair_citations(text, ctx.evidence, cited)
        cited += auto_cited
        if status != "error" and not text.strip():
            text = "Sorry, I couldn't put together an answer. Could you rephrase?"
        cards = self._cards(cited)
        constraint_warnings = check_constraints(cards, parse_hard_constraints(question))
        for w in constraint_warnings:
            for c in cards:
                if c["ref"] == w["ref"]:
                    c.setdefault("warnings", []).append(w["issue"])
        sources = [{"ref": r, **{k: v for k, v in ctx.evidence[r].items() if k != "carried"}}
                   for r in cited if not r.startswith("listing:")]
        latency = int((time.perf_counter() - started) * 1000)
        cost = estimate_cost(self.llm.name, self.llm.model, usage["prompt_tokens"], usage["completion_tokens"])
        if cards:
            yield AgentEvent("listing_cards", {"cards": cards})
        if sources:
            yield AgentEvent("citations", {"items": sources})
        done = {"text": text, "status": status, "citations": cited, "unsupported_citations": unsupported,
                "auto_citations": auto_cited, "constraint_warnings": constraint_warnings,
                "pending_actions": ctx.pending_actions, "tool_calls": trace, "llm_steps": steps,
                "usage": {**usage, "cost_usd": cost}, "latency_ms": latency, "request_id": request_id,
                "evidence": sorted(ctx.evidence)}
        self._persist(request_id, user_id, question, done, error)
        yield AgentEvent("done", done)

    def _forced_answer(self, convo: list[dict], request_id: str, ctx: ToolContext, error: LLMError):
        from llm.base import LLMResponse
        log.warning("forced final answer failed (%s); retrying text-only", error)
        try:
            return self.llm.chat([*convo, {"role": "user", "content": "Write your final answer to my question now, "
                                           "as plain text with citations. Do not call any tool."}],
                                 None, purpose="agent", request_id=request_id, temperature=0, max_tokens=900)
        except LLMError:
            listings = [(r, i) for r, i in ctx.evidence.items() if r.startswith("listing:") and i.get("title")][:4]
            if not listings:
                return LLMResponse("I couldn't finish this answer. Please try asking again more specifically.")
            lines = "\n".join(f"- {i['title']} ({i.get('area', '')}) [{r}]" for r, i in listings)
            return LLMResponse(f"I ran out of steps before writing a full answer. These were the most relevant "
                               f"listings I found:\n{lines}")

    def _cards(self, cited: list[str]) -> list[dict]:
        ids = [int(r.split(":")[1]) for r in cited if r.startswith("listing:")]
        if not ids:
            return []
        db = SessionLocal()
        try:
            by_id = {p.id: p for p in property_svc.get_properties(db, ids)}
            return [{**property_svc.public_summary(by_id[i]), "ref": f"listing:{i}", "url": f"/property/{i}"}
                    for i in ids if i in by_id]
        finally:
            db.close()

    def _persist(self, request_id, user_id, question, done, error) -> None:
        db = SessionLocal()
        try:
            db.add(AgentRun(request_id=request_id, user_id=user_id, provider=self.llm.name, model=self.llm.model,
                            question=question[:4000], answer=done["text"], tool_calls=done["tool_calls"],
                            citations=done["citations"], unsupported_citations=done["unsupported_citations"],
                            llm_steps=done["llm_steps"], prompt_tokens=done["usage"]["prompt_tokens"],
                            completion_tokens=done["usage"]["completion_tokens"], cost_usd=done["usage"]["cost_usd"],
                            latency_ms=done["latency_ms"], status=done["status"], error=error))
            db.commit()
        except Exception as e:  # noqa: BLE001
            log.warning("could not persist agent run: %s", e)
        finally:
            db.close()


def run_to_completion(agent: Agent, messages: list[dict], **kw) -> dict:
    """Collect a full turn (used by the non-streaming API and the eval runner)."""
    out: dict = {"steps": [], "tokens": []}
    for ev in agent.run(messages, **kw):
        if ev.type == "step":
            out["steps"].append(ev.data)
        elif ev.type == "token":
            out["tokens"].append(ev.data["text"])
        elif ev.type == "done":
            out.update(ev.data)
        elif ev.type == "error":
            out["error"] = ev.data
        elif ev.type in ("listing_cards", "citations"):
            out[ev.type] = ev.data
    return out
