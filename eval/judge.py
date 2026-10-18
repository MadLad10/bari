"""LLM-as-judge for citation support: does the cited evidence actually back the claim it's attached to?"""
from __future__ import annotations

import json
import re

from llm.base import LLMError

PROMPT = """You check citations in a housing assistant's answer. For each item you get a CLAIM (the sentence that
cites a source) and the EVIDENCE text of that source. Answer whether the evidence supports the claim's
facts about that source (prices, places, amenities, safety, experiences). Ignore style. Reply with JSON only:
{"verdicts": [{"i": 0, "supported": true|false, "why": "short"}]}"""

_SENT = re.compile(r"[^.!?।\n]*\[[^\]]+\][^.!?।\n]*[.!?।]?")


def claims_with_refs(answer: str) -> list[tuple[str, str]]:
    pairs = []
    for sent in _SENT.findall(answer or ""):
        for kind, num in re.findall(r"(listing|post|comment|safety):(\d+)", sent):
            pairs.append((sent.strip(), f"{kind}:{num}"))
    return pairs


def judge_citations(llm, answer: str, evidence_text: dict[str, str], request_id: str | None = None) -> dict:
    pairs = [(c, r) for c, r in claims_with_refs(answer) if r in evidence_text][:8]
    if not pairs:
        return {"judged": 0, "supported": 0}
    items = [{"i": i, "claim": c, "evidence": evidence_text[r][:1200]} for i, (c, r) in enumerate(pairs)]
    try:
        resp = llm.chat([{"role": "system", "content": PROMPT},
                         {"role": "user", "content": json.dumps(items, ensure_ascii=False)}],
                        purpose="eval_judge", request_id=request_id, json_mode=True, temperature=0, max_tokens=600)
        verdicts = json.loads(resp.content).get("verdicts", [])
    except (LLMError, json.JSONDecodeError, AttributeError):
        return {"judged": 0, "supported": 0, "error": True}
    supported = sum(1 for v in verdicts if v.get("supported") is True)
    return {"judged": len(verdicts), "supported": supported,
            "unsupported_claims": [pairs[v["i"]][0] for v in verdicts
                                   if v.get("supported") is False and isinstance(v.get("i"), int) and v["i"] < len(pairs)]}
