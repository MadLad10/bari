"""Estimated USD cost per call. Prices are USD per 1M tokens (input, output), paid-tier list prices.

Groq's free tier costs nothing, but the paid-tier price is logged anyway, so the eval can report what
the agent would cost in production. Override or extend with LLM_PRICES_JSON in .env, e.g.
LLM_PRICES_JSON={"my-model": [0.2, 0.6]}
"""
import json

from config import settings

PRICES: dict[str, tuple[float, float]] = {
    # Groq
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "llama-3.1-8b-instant": (0.05, 0.08),
    "openai/gpt-oss-120b": (0.15, 0.75),
    "openai/gpt-oss-20b": (0.10, 0.50),
    "qwen/qwen3-32b": (0.29, 0.59),
    "moonshotai/kimi-k2-instruct": (1.00, 3.00),
    # OpenAI
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-mini": (0.40, 1.60),
}


def _prices() -> dict[str, tuple[float, float]]:
    extra = json.loads(settings.llm_prices_json) if settings.llm_prices_json else {}
    return {**PRICES, **{k: tuple(v) for k, v in extra.items()}}


def estimate_cost(provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> float:
    if provider in ("ollama", "fake"):
        return 0.0  # local inference: no per-token cost
    p_in, p_out = _prices().get(model, (0.0, 0.0))
    return round((prompt_tokens * p_in + completion_tokens * p_out) / 1_000_000, 8)
