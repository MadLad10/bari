from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from deps import get_current_user
from models import User
from services import safety as svc

router = APIRouter(prefix="/safety", tags=["safety"])


class VoteIn(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = Field(None, max_length=300)
    voter_name: str | None = None


class SafetyStats(BaseModel):
    property_id: int
    avg_score: float | None
    vote_count: int
    votes: list[dict]


@router.post("/{property_id}/vote", status_code=201)
def submit_vote(property_id: int, payload: VoteIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    _, avg = svc.submit_vote(db, property_id, **payload.model_dump(), voter_id=user.id)
    return {"avg_score": avg}


@router.get("/{property_id}", response_model=SafetyStats)
def get_safety(property_id: int, db: Session = Depends(get_db)):
    return svc.get_safety_stats(db, property_id)
