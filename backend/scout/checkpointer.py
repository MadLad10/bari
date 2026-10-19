"""LangGraph's Postgres checkpointer on bari's own database: a paused hunt survives restarts, deploys and
serverless cold starts, and resumes when the student decides.

The checkpoint tables are created by an Alembic migration (setup() needs autocommit and waits for every open
transaction, so it must not run inside a request)."""
from __future__ import annotations

from contextlib import contextmanager

from config import settings


def conninfo() -> str:
    url = settings.checkpoint_database_url or settings.database_url
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


@contextmanager
def open_checkpointer():
    """A PostgresSaver on its own connection, closed afterwards.

    prepare_threshold=None: no server-side prepared statements, which transaction-mode poolers (Neon) reject."""
    import psycopg
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row

    conn = psycopg.connect(conninfo(), autocommit=True, prepare_threshold=None, row_factory=dict_row)
    try:
        yield PostgresSaver(conn)
    finally:
        conn.close()
