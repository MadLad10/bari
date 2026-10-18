"""Per-request context shared by the HTTP middleware, the agent and LLM call logging."""
from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
