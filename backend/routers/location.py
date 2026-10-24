from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from deps import get_current_user_optional
from models import User, UserRole
from services import location as svc
from services.properties import get_property
from services.publication import is_public
from services.errors import NotFound

router = APIRouter(prefix="/properties", tags=["location"])


def visible_property(db, property_id, user):
    prop = get_property(db, property_id)
    if not is_public(prop) and (not user or user.id != prop.owner_id and user.role != UserRole.admin):
        raise NotFound("Property not found")
    return prop


@router.get("/{property_id}/nearby")
def nearby(property_id: int, db: Session = Depends(get_db), user: User | None = Depends(get_current_user_optional)):
    return svc.nearby(visible_property(db, property_id, user))


class Destination(BaseModel):
    destination_id: str = Field(pattern=r"^(node|way|relation)/[0-9]+$", max_length=60)


@router.post("/{property_id}/route")
def route(property_id: int, payload: Destination, db: Session = Depends(get_db),
          user: User | None = Depends(get_current_user_optional)):
    return svc.route(visible_property(db, property_id, user), payload.destination_id)
