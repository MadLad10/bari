"""Agentic background workflows: listing assistant, listing screening (duplicates/scams) and content
moderation. Deterministic rules make the decision, and an LLM adds a second opinion when available.
Every decision is logged with its reasons in `moderation_decisions`."""
