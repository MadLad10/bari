"""Account-bound renter conversations shared by HTTP and WebSocket transports."""
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from services.publication import is_public
from models import ChatMessage, ListingStatus, Property, SenderType, User, UserRole
from services.errors import BadRequest, Forbidden, NotFound
from services.properties import get_property


class MessageIn(BaseModel):
    property_id: int
    session_token: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=1, max_length=5000)
    # Old client identity fields are ignored; the account supplies both.
    sender: SenderType | None = None
    sender_name: str | None = None


def authorize(db: Session, property_id: int, session_token: str, user: User) -> SenderType:
    prop = get_property(db, property_id)
    if user.id == prop.owner_id or user.role == UserRole.admin:
        return SenderType.owner
    if session_token != f"user-{user.id}":
        raise Forbidden("This conversation belongs to another account")
    if not is_public(prop):
        if not db.query(ChatMessage.id).filter_by(property_id=property_id, session_token=session_token).first():
            raise NotFound("Property not found")
    return SenderType.renter


def messages(db: Session, property_id: int, session_token: str, user: User) -> list[ChatMessage]:
    authorize(db, property_id, session_token, user)
    return (db.query(ChatMessage).filter_by(property_id=property_id, session_token=session_token)
            .order_by(ChatMessage.created_at, ChatMessage.id).all())


def send(db: Session, payload: MessageIn, user: User) -> ChatMessage:
    sender = authorize(db, payload.property_id, payload.session_token, user)
    if not payload.content.strip():
        raise BadRequest("Enter a message")
    if sender == SenderType.owner and not db.query(ChatMessage.id).filter_by(
            property_id=payload.property_id, session_token=payload.session_token).first():
        raise NotFound("This conversation has not been started by a renter")
    msg = ChatMessage(property_id=payload.property_id, session_token=payload.session_token,
                      sender=sender, sender_name=user.name, content=payload.content.strip())
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def inbox(db: Session, user: User) -> list[dict]:
    latest = (db.query(ChatMessage.property_id, ChatMessage.session_token, func.max(ChatMessage.id).label("id"))
              .join(Property, Property.id == ChatMessage.property_id).filter(Property.owner_id == user.id)
              .group_by(ChatMessage.property_id, ChatMessage.session_token).subquery())
    rows = (db.query(ChatMessage, Property.title).join(latest, ChatMessage.id == latest.c.id)
            .join(Property, Property.id == ChatMessage.property_id).order_by(ChatMessage.created_at.desc()).all())
    result = []
    for msg, title in rows:
        first = (db.query(ChatMessage).filter_by(property_id=msg.property_id, session_token=msg.session_token,
                                                sender=SenderType.renter).order_by(ChatMessage.id).first())
        result.append({"property_id": msg.property_id, "property_title": title, "session_token": msg.session_token,
                       "renter_name": first.sender_name if first else "Renter", "last_message": msg.content,
                       "last_sender": msg.sender.value, "updated_at": msg.created_at.isoformat()})
    return result


def to_out(msg: ChatMessage) -> dict:
    return {"id": msg.id, "property_id": msg.property_id, "session_token": msg.session_token,
            "sender": msg.sender.value, "sender_name": msg.sender_name, "content": msg.content,
            "created_at": msg.created_at.isoformat() if msg.created_at else ""}
