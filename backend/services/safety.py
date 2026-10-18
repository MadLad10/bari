from sqlalchemy import func
from sqlalchemy.orm import Session

from models import SafetyVote
from jobs.queue import enqueue
from rag.indexer import enqueue_index
from services.properties import get_property


def submit_vote(db: Session, property_id: int, rating: int, comment: str | None = None,
                voter_name: str | None = None, **extra) -> tuple[SafetyVote, float]:
    prop = get_property(db, property_id)
    vote = SafetyVote(property_id=property_id, rating=rating, comment=comment, voter_name=voter_name, **extra)
    db.add(vote)
    db.flush()  # session has autoflush=False; the new vote must count toward the average

    # update the denormalised safety_score on the property
    result = db.query(func.avg(SafetyVote.rating)).filter(SafetyVote.property_id == property_id).scalar()
    new_avg = round(float(result or rating), 2)
    prop.safety_score = new_avg
    if comment:
        enqueue_index(db, "safety", vote.id)
        enqueue(db, "moderate", {"kind": "safety", "id": vote.id}, dedupe_key=f"moderate:safety:{vote.id}")
    db.commit()
    db.refresh(vote)
    return vote, new_avg


def get_safety_stats(db: Session, property_id: int, limit: int = 20) -> dict:
    votes = (
        db.query(SafetyVote)
        .filter(SafetyVote.property_id == property_id)
        .order_by(SafetyVote.created_at.desc(), SafetyVote.id.desc())
        .limit(limit)
        .all()
    )
    avg, total = db.query(func.avg(SafetyVote.rating), func.count(SafetyVote.id)).filter(
        SafetyVote.property_id == property_id
    ).one()
    return {
        "property_id": property_id,
        "avg_score": round(float(avg), 2) if avg else None,
        "vote_count": total,
        "votes": [
            {
                "id": v.id,
                "rating": v.rating,
                "comment": v.comment if v.moderation_status == "visible" else None,
                "voter_name": v.voter_name or "Anonymous",
                "created_at": v.created_at.isoformat() if v.created_at else "",
            }
            for v in votes
        ],
    }
