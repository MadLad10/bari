"""AI assistant: a tool-calling agent streamed over Server-Sent Events."""
import json
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from agent.loop import Agent, AgentEvent, run_to_completion
from deps import get_current_user_optional
from llm.base import LLMError
from llm.client import get_llm
from llm.context import request_id_var
from models import User

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


@router.post("/chat")
def chat(payload: ChatRequest, user: User | None = Depends(get_current_user_optional)):
    try:
        agent = Agent(get_llm(payload.provider))
    except LLMError as e:  # e.g. no API key configured: tell the UI instead of failing the request
        event = AgentEvent("error", {"message": "The assistant isn't configured on this server.", "detail": str(e)})
        if not payload.stream:
            return JSONResponse(status_code=503, content=event.data)
        return StreamingResponse(iter([sse(event)]), media_type="text/event-stream")
    messages = [m.model_dump() for m in payload.messages]
    # Captured now: the streaming body runs after the request-ID middleware has reset its contextvar.
    kwargs = {"user_id": user.id if user else None, "request_id": request_id_var.get()}
    if not payload.stream:
        return run_to_completion(agent, messages, **kwargs)
    return StreamingResponse((sse(ev) for ev in agent.run(messages, **kwargs)), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
