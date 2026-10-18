from sqlalchemy import inspect, text

from database import engine


def test_migrations_create_tables_and_extensions():
    insp = inspect(engine)
    assert {"properties", "bookings", "safety_votes", "forum_posts", "forum_comments",
            "chat_messages", "alembic_version"} <= set(insp.get_table_names())
    with engine.connect() as conn:
        exts = {r[0] for r in conn.execute(text("select extname from pg_extension"))}
    assert {"vector", "pg_trgm"} <= exts
