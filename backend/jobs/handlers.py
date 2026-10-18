"""Job handlers. Importing this module registers them."""
from sqlalchemy.orm import Session

from jobs.queue import handler
from rag.indexer import index_source


@handler("index")
def index_job(db: Session, payload: dict) -> dict:
    return index_source(db, payload["source_type"], payload["source_id"])
