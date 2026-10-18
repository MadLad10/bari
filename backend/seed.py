"""Load the synthetic fixtures in seed_data/*.json into the database.

    python seed.py            # seed if the database is empty
    python seed.py --reset    # wipe all app tables first

Regenerate the fixtures with `python -m seed_data.generate` (deterministic).
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

import models  # noqa: F401  registers tables
from database import Base, SessionLocal, engine
from models import Booking, ForumComment, ForumPost, Property, SafetyVote, User, UserRole
from services.users import hash_password

DATA = Path(__file__).resolve().parent / "seed_data"

# Demo accounts for local development. Documented in README; never use in production.
DEMO_PASSWORD = "bari-demo-123"
DEMO_USERS = [
    {"email": "student@example.com", "name": "Nusrat Jahan", "phone": "01700000001", "role": UserRole.renter},
    {"email": "owner@example.com", "name": "Karim Hossain", "phone": "01711000001", "role": UserRole.owner},
    {"email": "admin@example.com", "name": "bari admin", "phone": None, "role": UserRole.admin},
]
DEMO_OWNER_LISTINGS = range(1, 9)  # the original 8 sample listings

# Fixture-only keys that are not table columns.
_META = {"lang", "needle", "available_from", "comments"}


def _load(name: str) -> list[dict]:
    return json.loads((DATA / f"{name}.json").read_text())


def _row(d: dict) -> dict:
    row = {k: v for k, v in d.items() if k not in _META}
    for k in ("created_at", "check_in", "check_out"):
        if isinstance(row.get(k), str):
            row[k] = datetime.fromisoformat(row[k])
    return row


def _reset_sequences(db) -> None:
    for table in ("users", "properties", "forum_posts", "forum_comments", "safety_votes", "bookings"):
        db.execute(text(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)"
        ))


def reset(db) -> None:
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    db.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    db.commit()


def seed(db, force: bool = False) -> dict[str, int]:
    if not force and db.query(Property).count() > 0:
        return {}
    listings, posts = _load("listings"), _load("posts")
    votes, bookings = _load("safety_votes"), _load("bookings")

    pw = hash_password(DEMO_PASSWORD)
    users = [User(password_hash=pw, **u) for u in DEMO_USERS]
    db.add_all(users)
    db.flush()
    owner = next(u for u in users if u.role == UserRole.owner)

    db.add_all(Property(**_row(l), owner_id=owner.id if l["id"] in DEMO_OWNER_LISTINGS else None)
               for l in listings)
    db.flush()
    db.add_all(ForumPost(**_row(p)) for p in posts)
    db.flush()
    db.add_all(ForumComment(**_row(c)) for p in posts for c in p["comments"])
    db.add_all(SafetyVote(**_row(v)) for v in votes)
    db.add_all(Booking(**_row(b)) for b in bookings)
    db.flush()
    _reset_sequences(db)
    db.commit()
    return {"users": len(users), "properties": len(listings), "posts": len(posts),
            "comments": sum(len(p["comments"]) for p in posts),
            "safety_votes": len(votes), "bookings": len(bookings)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true", help="truncate all app tables before seeding")
    args = ap.parse_args()
    db = SessionLocal()
    try:
        if args.reset:
            reset(db)
        counts = seed(db, force=args.reset)
        print(f"Seeded: {counts}" if counts else "Database already seeded (use --reset to reload).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
