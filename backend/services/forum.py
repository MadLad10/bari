from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from models import ForumComment, ForumPost, PostType
from services.errors import NotFound


def post_to_dict(post: ForumPost, comment_count: int) -> dict:
    return {
        "id": post.id,
        "title": post.title,
        "body": post.body,
        "post_type": post.post_type,
        "area": post.area,
        "nearby_university": post.nearby_university,
        "author_name": post.author_name,
        "upvotes": post.upvotes,
        "property_id": post.property_id,
        "created_at": post.created_at.isoformat() if post.created_at else "",
        "comment_count": comment_count,
    }


def comment_to_dict(c: ForumComment) -> dict:
    return {
        "id": c.id,
        "post_id": c.post_id,
        "author_name": c.author_name,
        "content": c.content,
        "created_at": c.created_at.isoformat() if c.created_at else "",
    }


def _comment_counts(db: Session, post_ids: list[int]) -> dict[int, int]:
    if not post_ids:
        return {}
    rows = (
        db.query(ForumComment.post_id, func.count(ForumComment.id))
        .filter(ForumComment.post_id.in_(post_ids))
        .group_by(ForumComment.post_id)
        .all()
    )
    return dict(rows)


def list_posts(db: Session, post_type: PostType | None = None, area: str | None = None,
               nearby_university: str | None = None, q: str | None = None,
               skip: int = 0, limit: int = 20) -> list[dict]:
    query = db.query(ForumPost)
    if post_type:
        query = query.filter(ForumPost.post_type == post_type)
    if area:
        query = query.filter(ForumPost.area.ilike(f"%{area}%"))
    if nearby_university:
        query = query.filter(ForumPost.nearby_university.ilike(f"%{nearby_university}%"))
    if q:
        query = query.filter(or_(ForumPost.title.ilike(f"%{q}%"), ForumPost.body.ilike(f"%{q}%")))
    posts = query.order_by(ForumPost.created_at.desc(), ForumPost.id.desc()).offset(skip).limit(limit).all()
    counts = _comment_counts(db, [p.id for p in posts])
    return [post_to_dict(p, counts.get(p.id, 0)) for p in posts]


def get_post_model(db: Session, post_id: int) -> ForumPost:
    post = db.get(ForumPost, post_id)
    if not post:
        raise NotFound("Post not found")
    return post


def get_post(db: Session, post_id: int) -> dict:
    post = get_post_model(db, post_id)
    return post_to_dict(post, _comment_counts(db, [post_id]).get(post_id, 0))


def create_post(db: Session, **fields) -> dict:
    post = ForumPost(**fields)
    db.add(post)
    db.commit()
    db.refresh(post)
    return post_to_dict(post, 0)


def upvote_post(db: Session, post_id: int) -> int:
    post = get_post_model(db, post_id)
    post.upvotes += 1
    db.commit()
    return post.upvotes


def list_comments(db: Session, post_id: int) -> list[dict]:
    comments = (
        db.query(ForumComment)
        .filter(ForumComment.post_id == post_id)
        .order_by(ForumComment.created_at, ForumComment.id)
        .all()
    )
    return [comment_to_dict(c) for c in comments]


def add_comment(db: Session, post_id: int, **fields) -> dict:
    get_post_model(db, post_id)
    comment = ForumComment(post_id=post_id, **fields)
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment_to_dict(comment)
