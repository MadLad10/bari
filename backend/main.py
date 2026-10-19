import logging
import os
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from config import settings
from llm.base import LLMError
from llm.context import request_id_var
from routers import actions, admin, ai, auth, bookings, chat, forum, hunts, listing_assistant, properties, safety, search
from services.errors import ServiceError

# Schema is managed by Alembic (`alembic upgrade head`), not create_all.
app = FastAPI(title="bari.com API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Tag every request with an ID (client-supplied X-Request-ID or a new one) for LLM call logs."""
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex
    token = request_id_var.set(rid[:64])
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = rid[:64]
    return response


@app.middleware("http")
async def inline_jobs_middleware(request: Request, call_next):
    """JOBS_MODE=inline: run the jobs a write request queued (index, screen, moderate) before answering.

    On Vercel nothing runs after the response is sent, so the jobs go first. Locally the worker does this."""
    response = await call_next(request)
    if settings.jobs_mode == "inline" and request.method in ("POST", "PUT", "PATCH", "DELETE") \
            and not request.url.path.startswith("/api/ai/"):
        from starlette.concurrency import run_in_threadpool
        await run_in_threadpool(_run_queued_jobs)
    return response


def _run_queued_jobs() -> None:
    from database import SessionLocal
    from jobs.queue import run_pending
    db = SessionLocal()
    try:
        run_pending(db, limit=20)
    except Exception:  # noqa: BLE001  a failed job is retried later; never fail the user's request
        logging.getLogger("bari.jobs").exception("inline job run failed")
    finally:
        db.close()


@app.exception_handler(LLMError)
async def llm_error_handler(_: Request, exc: LLMError):
    return JSONResponse(status_code=503, content={"detail": f"AI provider unavailable: {exc}"})


@app.exception_handler(ServiceError)
async def service_error_handler(_: Request, exc: ServiceError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


os.makedirs(settings.upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

for r in (auth, properties, bookings, chat, ai, actions, safety, forum, search, listing_assistant, admin, hunts):
    app.include_router(r.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}
