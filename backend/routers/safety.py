from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, Field
from typing import Optional

from database import get_db
from models import SafetyVote, Property

router = APIRouter(prefix="/safety", tags=["safety"])


class VoteIn(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=300)
    voter_name: Optional[str] = None


class SafetyStats(BaseModel):
    property_id: int
    avg_score: Optional[float]
    vote_count: int
    votes: list[dict]


@router.post("/{property_id}/vote", status_code=201)
def submit_vote(property_id: int, payload: VoteIn, db: Session = Depends(get_db)):
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    vote = SafetyVote(property_id=property_id, **payload.model_dump())
    db.add(vote)
    db.flush()  # session has autoflush=False; the new vote must count toward the average

    # update denormalised safety_score on the property
    result = db.query(func.avg(SafetyVote.rating)).filter(
        SafetyVote.property_id == property_id
    ).scalar()
    new_avg = round(float(result or payload.rating), 2)
    prop.safety_score = new_avg

    db.commit()
    return {"avg_score": new_avg}


@router.get("/{property_id}", response_model=SafetyStats)
def get_safety(property_id: int, db: Session = Depends(get_db)):
    votes = (
        db.query(SafetyVote)
        .filter(SafetyVote.property_id == property_id)
        .order_by(SafetyVote.created_at.desc())
        .limit(20)
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
                "rating": v.rating,
                "comment": v.comment,
                "voter_name": v.voter_name or "Anonymous",
                "created_at": v.created_at.isoformat() if v.created_at else "",
            }
            for v in votes
        ],
    }
