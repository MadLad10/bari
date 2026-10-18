from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import PostType
from services import forum as svc

router = APIRouter(prefix="/forum", tags=["forum"])


class PostIn(BaseModel):
    title: str = Field(..., min_length=5, max_length=200)
    body: str = Field(..., min_length=10)
    post_type: PostType
    area: str | None = None
    nearby_university: str | None = None
    author_name: str = Field(..., min_length=2)
    property_id: int | None = None


class PostOut(BaseModel):
    id: int
    title: str
    body: str
    post_type: PostType
    area: str | None
    nearby_university: str | None
    author_name: str
    upvotes: int
    property_id: int | None
    created_at: str
    comment_count: int = 0


class CommentIn(BaseModel):
    author_name: str = Field(..., min_length=2)
    content: str = Field(..., min_length=2)


class CommentOut(BaseModel):
    id: int
    post_id: int
    author_name: str
    content: str
    created_at: str


@router.get("/", response_model=list[PostOut])
def list_posts(
    post_type: PostType | None = None,
    area: str | None = None,
    nearby_university: str | None = None,
    q: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, le=100),
    db: Session = Depends(get_db),
):
    return svc.list_posts(db, post_type, area, nearby_university, q, skip, limit)


@router.post("/", response_model=PostOut, status_code=201)
def create_post(payload: PostIn, db: Session = Depends(get_db)):
    return svc.create_post(db, **payload.model_dump())


@router.get("/{post_id}", response_model=PostOut)
def get_post(post_id: int, db: Session = Depends(get_db)):
    return svc.get_post(db, post_id)


@router.post("/{post_id}/upvote")
def upvote_post(post_id: int, db: Session = Depends(get_db)):
    return {"upvotes": svc.upvote_post(db, post_id)}


@router.get("/{post_id}/comments", response_model=list[CommentOut])
def get_comments(post_id: int, db: Session = Depends(get_db)):
    return svc.list_comments(db, post_id)


@router.post("/{post_id}/comments", response_model=CommentOut, status_code=201)
def add_comment(post_id: int, payload: CommentIn, db: Session = Depends(get_db)):
    return svc.add_comment(db, post_id, **payload.model_dump())
