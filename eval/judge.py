"""LLM-as-judge for citation support: does the cited evidence actually back the claim it's attached to?"""
from __future__ import annotations

import json
import re

from llm.base import LLMError

PROMPT = """You check citations in a housing assistant's answer. For each item you get a CLAIM (a sentence that
cites sources) and the EVIDENCE text of every source it cites. Answer whether the evidence, taken together,
supports the claim's facts (prices, places, distances, amenities, safety, experiences). Statements that something
is absent ("meals not listed") count as supported when the evidence indeed doesn't mention it. Ignore style and
wording differences. Reply with JSON only:
{"verdicts": [{"i": 0, "supported": true|false, "why": "short"}]}"""

# Sentence/bullet boundaries: . ! ? । followed by whitespace (so "0.6 km" stays whole) or a newline.
_SPLIT = re.compile(r"(?<=[.!?।])\s+|\n+")
_REF = re.compile(r"(listing|post|comment|safety):(\d+)")


def claims_with_refs(answer: str) -> list[tuple[str, list[str]]]:
    """(claim, [refs it cites]). A claim citing several sources is judged against all of them together."""
    out = []
    for sent in _SPLIT.split(answer or ""):
        refs = list(dict.fromkeys(f"{k}:{n}" for k, n in _REF.findall(sent)))
        if refs and sent.strip():
            out.append((sent.strip(), refs))
    return out


def judge_citations(llm, answer: str, evidence_text: dict[str, str], request_id: str | None = None) -> dict:
    pairs = [(c, [r for r in refs if r in evidence_text]) for c, refs in claims_with_refs(answer)]
    pairs = [(c, refs) for c, refs in pairs if refs][:8]
    if not pairs:
        return {"judged": 0, "supported": 0}
    items = [{"i": i, "claim": c, "evidence": "\n---\n".join(f"[{r}] {evidence_text[r][:900]}" for r in refs)}
             for i, (c, refs) in enumerate(pairs)]
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
