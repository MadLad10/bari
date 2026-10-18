"""Run duplicate/scam screening over existing listings (new listings are screened automatically).

    python -m scripts.screen_listings --dry-run     # report only
    python -m scripts.screen_listings               # apply: flagged listings go to `pending`
"""
import argparse
from collections import Counter

from database import SessionLocal
from models import ListingStatus, Property
from workflows.screening import screen_listing


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("ids", nargs="*", type=int)
    args = ap.parse_args()
    db = SessionLocal()
    try:
        ids = args.ids or [i for (i,) in db.query(Property.id).filter(Property.status == ListingStatus.active)
                           .order_by(Property.created_at, Property.id)]
        labels, flagged = Counter(), 0
        for pid in ids:
            r = screen_listing(db, pid, apply=not args.dry_run)
            if r.get("decision") == "flag":
                flagged += 1
                labels.update(r["labels"])
                print(f"FLAG listing:{pid}: {'; '.join(r['reasons'])}")
        print(f"screened {len(ids)}, flagged {flagged}, labels {dict(labels)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
