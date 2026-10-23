"""Job handlers. Importing this module registers them."""
from sqlalchemy.orm import Session

from jobs.queue import handler
from rag.indexer import index_source


@handler("verify_documents")
def verify_documents_job(db: Session, payload: dict) -> dict:
    from services.verification import verify_documents
    return verify_documents(db, payload["property_id"])


@handler("index")
def index_job(db: Session, payload: dict) -> dict:
    return index_source(db, payload["source_type"], payload["source_id"])


@handler("screen_listing")
def screen_listing_job(db: Session, payload: dict) -> dict:
    from workflows.screening import screen_listing
    return screen_listing(db, payload["property_id"])


@handler("moderate")
def moderate_job(db: Session, payload: dict) -> dict:
    from workflows.moderation import moderate
    return moderate(db, payload["kind"], payload["id"])


@handler("scout_run")
def scout_run_job(db: Session, payload: dict) -> dict:
    from scout.service import run_hunt
    return {"run_id": run_hunt(payload["hunt_id"], payload.get("trigger", "schedule"))}
