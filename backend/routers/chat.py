import asyncio

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from database import get_db, SessionLocal
from deps import get_current_user, require_role
from models import User, UserRole
from services import chat as svc
from services.chat import MessageIn
from services.errors import ServiceError
from services.users import user_from_token

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/inbox")
def inbox(db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.owner))):
    return svc.inbox(db, user)


@router.get("/{property_id}/{session_token}")
def get_messages(property_id: int, session_token: str, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    return [svc.to_out(m) for m in svc.messages(db, property_id, session_token, user)]


@router.post("/", status_code=201)
def post_message(payload: MessageIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.to_out(svc.send(db, payload, user))


def _socket_read(token, property_id, session_token):
    with SessionLocal() as db:
        user = user_from_token(db, token)
        return [svc.to_out(m) for m in svc.messages(db, property_id, session_token, user)]


def _socket_send(token, payload):
    with SessionLocal() as db:
        return svc.to_out(svc.send(db, payload, user_from_token(db, token)))


@router.websocket("/ws/{property_id}/{session_token}")
async def websocket_chat(websocket: WebSocket, property_id: int, session_token: str):
    await websocket.accept()
    try:
        # JWTs go in the first frame, never in URLs or access logs.
        auth = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        token = auth.get("token", "")
        initial = await run_in_threadpool(_socket_read, token, property_id, session_token)
        await websocket.send_json({"type": "ready"})
        seen = {m["id"] for m in initial}
        for msg in initial:
            await websocket.send_json(msg)
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=1)
                try:
                    payload = MessageIn(property_id=property_id, session_token=session_token, content=data.get("content", ""))
                    await run_in_threadpool(_socket_send, token, payload)
                except ValidationError:
                    await websocket.send_json({"error": "Enter a message of up to 5,000 characters"})
                except ServiceError as exc:
                    if exc.status_code in (401, 403, 404):
                        raise
                    await websocket.send_json({"error": exc.detail})
            except asyncio.TimeoutError:
                pass
            # Database fanout includes REST/Scout messages and works across workers.
            rows = await run_in_threadpool(_socket_read, token, property_id, session_token)
            for msg in rows:
                if msg["id"] not in seen:
                    await websocket.send_json(msg)
                    seen.add(msg["id"])
    except (ServiceError, asyncio.TimeoutError):
        await websocket.close(code=1008)
    except (ValueError, TypeError, AttributeError):
        await websocket.close(code=1008)
    except WebSocketDisconnect:
        pass
