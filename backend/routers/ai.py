"""AI assistant: a tool-calling agent streamed over Server-Sent Events."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from agent.loop import Agent, AgentEvent, run_to_completion
from deps import get_current_user_optional
from llm.base import LLMError
from llm.client import get_llm
from llm.context import request_id_var
from config import settings
from database import get_db
from models import AgentRun, User

router = APIRouter(prefix="/ai", tags=["ai"])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=8000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1, max_length=40)
    provider: Literal["api", "ollama"] | None = None
    stream: bool = True


def sse(event: AgentEvent) -> str:
    return f"event: {event.type}\ndata: {json.dumps(event.data, ensure_ascii=False, default=str)}\n\n"


def client_key(request: Request, user: User | None) -> str:
    """Who is asking, for rate limiting: the account if logged in, else a salted hash of the IP (no raw IPs stored)."""
    if user:
        return f"user:{user.id}"
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "?")
    return "ip:" + hashlib.sha256(f"{settings.jwt_secret}:{ip}".encode()).hexdigest()[:24]


def rate_limited(db: Session, key: str) -> bool:
    limit = settings.ai_rate_limit_per_hour
    if limit <= 0:
        return False
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    used = db.query(func.count(AgentRun.id)).filter(AgentRun.client_key == key, AgentRun.created_at >= since).scalar()
    return used >= limit


def _error(payload: ChatRequest, message: str, detail: str, status: int):
    """Errors reach the UI as an SSE `error` event (or JSON), not as a failed request."""
    event = AgentEvent("error", {"message": message, "detail": detail})
    if not payload.stream:
        return JSONResponse(status_code=status, content=event.data)
    return StreamingResponse(iter([sse(event)]), media_type="text/event-stream")


@router.post("/chat")
def chat(payload: ChatRequest, request: Request, user: User | None = Depends(get_current_user_optional),
         db: Session = Depends(get_db)):
    key = client_key(request, user)
    if rate_limited(db, key):
        return _error(payload, f"You've reached the demo limit of {settings.ai_rate_limit_per_hour} questions per "
                      "hour. Please try again later.", "rate limited", 429)
    try:
        agent = Agent(get_llm(payload.provider))
    except LLMError as e:  # e.g. no API key configured: tell the UI instead of failing the request
        return _error(payload, "The assistant isn't configured on this server.", str(e), 503)
    messages = [m.model_dump() for m in payload.messages]
    # Captured now: the streaming body runs after the request-ID middleware has reset its contextvar.
    kwargs = {"user_id": user.id if user else None, "request_id": request_id_var.get(), "client_key": key}
    if not payload.stream:
        return run_to_completion(agent, messages, **kwargs)
    return StreamingResponse((sse(ev) for ev in agent.run(messages, **kwargs)), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
