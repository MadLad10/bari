"""Turn a student's free-text brief into hunt criteria (LLM structured output, validated by Pydantic)."""
from __future__ import annotations

import json
from datetime import date

from pydantic import BaseModel, Field, ValidationError

from agent.tools import ListingFilters
from llm.base import LLMError
from llm.client import get_llm


class HuntDraft(BaseModel):
    title: str = Field(max_length=120)
    criteria: ListingFilters = Field(default_factory=ListingFilters)
    preferences: list[str] = Field(default_factory=list, max_length=8)
    questions: list[str] = Field(default_factory=list, max_length=6)
    move_in: date | None = None
    stay_months: int = Field(6, ge=1, le=24)


PARSE_PROMPT = """Turn a student's housing request in Dhaka into JSON for a saved search. Today is {today}.
Reply with JSON only, using exactly these keys:
{{"title": short title,
  "criteria": hard filters the student clearly stated, any of: max_price, min_price, bedrooms,
              nearby_university (one of: BRAC University, North South University, Dhaka University, BUET, IUB,
              AIUB, East West University, Jahangirnagar University), area, is_female_only, min_safety_score
              ("safe" ≈ 4), rental_type ("monthly" unless they want daily),
  "preferences": soft wishes in a few words each (e.g. "quiet street", "gas line"),
  "questions": things to ask owners that listings often don't say (e.g. "Is it line gas or cylinder?"),
  "move_in": "YYYY-MM-DD" or null (a month means its first day, the next one after today),
  "stay_months": number}}
Only include filters the student actually stated. "25k" means 25000."""


def parse_brief(brief: str, today: date | None = None) -> HuntDraft:
    today = today or date.today()
    try:
        llm = get_llm()
        resp = llm.chat([{"role": "system", "content": PARSE_PROMPT.format(today=today.isoformat())},
                         {"role": "user", "content": brief[:2000]}],
                        purpose="scout_parse", json_mode=True, temperature=0, max_tokens=500)
        data = json.loads(resp.content)
        data["criteria"] = {k: v for k, v in (data.get("criteria") or {}).items() if v not in (None, "")}
        return HuntDraft.model_validate(data)
    except (LLMError, json.JSONDecodeError, ValidationError, TypeError, AttributeError):
        # The student can always fill the form themselves; never block on the parser.
        return HuntDraft(title=brief.strip()[:60] or "My hunt")
