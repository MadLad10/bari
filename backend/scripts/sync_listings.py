"""Apply corrected listing text/location from the seed fixtures to an existing database and re-index them.

    python -m scripts.sync_listings 1 2 3
"""
import json
import sys

from database import SessionLocal
from models import Property
from rag.indexer import index_many
from seed import DATA

FIELDS = ("title", "description", "area", "address", "nearby_university", "university_distance_km")


def main() -> None:
    ids = {int(a) for a in sys.argv[1:]}
    if not ids:
        sys.exit(__doc__)
    fixtures = {l["id"]: l for l in json.loads((DATA / "listings.json").read_text()) if l["id"] in ids}
    db = SessionLocal()
    try:
        for pid, f in fixtures.items():
            prop = db.get(Property, pid)
            changes = {k: f[k] for k in FIELDS if getattr(prop, k) != f[k]}
            for k, v in changes.items():
                setattr(prop, k, v)
            print(f"listing {pid}: updated {sorted(changes) or 'nothing'}")
        db.commit()
        print("re-indexed:", index_many(db, [("listing", pid) for pid in fixtures]))
    finally:
        db.close()


if __name__ == "__main__":
    main()
