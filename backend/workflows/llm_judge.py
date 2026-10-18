"""LLM second opinion that returns JSON. Failures return None: workflows fall back to rules alone."""
from __future__ import annotations

import json
import logging

from llm.base import LLMError
from llm.client import get_llm

log = logging.getLogger("bari.workflows")


def judge(purpose: str, system: str, payload: dict, request_id: str | None = None) -> tuple[dict | None, str | None]:
    """Returns (parsed JSON or None, model name or None)."""
    try:
        llm = get_llm()
        resp = llm.chat([{"role": "system", "content": system},
                         {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                        purpose=purpose, request_id=request_id, json_mode=True, temperature=0, max_tokens=300)
        data = json.loads(resp.content)
        return (data if isinstance(data, dict) else None), llm.model
    except (LLMError, json.JSONDecodeError, ValueError) as e:
        log.warning("%s: LLM second opinion unavailable: %s", purpose, e)
        return None, None
