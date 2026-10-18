from sqlalchemy import inspect, text

from database import engine


def test_migrations_create_tables_and_extensions():
    insp = inspect(engine)
    assert {"properties", "bookings", "safety_votes", "forum_posts", "forum_comments",
            "chat_messages", "alembic_version"} <= set(insp.get_table_names())
    with engine.connect() as conn:
        exts = {r[0] for r in conn.execute(text("select extname from pg_extension"))}
    assert {"vector", "pg_trgm"} <= exts


def test_migrations_round_trip():
    """Every migration must downgrade cleanly and re-apply."""
    from tests.conftest import BACKEND
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    command.downgrade(cfg, "base")
    assert "properties" not in inspect(engine).get_table_names()
    command.upgrade(cfg, "head")
    assert "users" in inspect(engine).get_table_names()
