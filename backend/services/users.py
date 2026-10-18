from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from sqlalchemy.orm import Session

from config import settings
from models import Booking, Property, User, UserRole
from services.errors import BadRequest, Conflict, Forbidden, NotFound


class Unauthorized(Forbidden):
    status_code = 401


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=settings.bcrypt_rounds)).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_user(db: Session, email: str, password: str, name: str, phone: str | None = None,
                role: UserRole = UserRole.renter) -> User:
    email = email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise Conflict("An account with this email already exists")
    user = User(email=email, password_hash=hash_password(password), name=name, phone=phone, role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if not user or not verify_password(password, user.password_hash):
        raise Unauthorized("Invalid email or password")
    return user


def create_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user.id), "role": user.role.value, "iat": now,
               "exp": now + timedelta(minutes=settings.jwt_expire_minutes)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def user_from_token(db: Session, token: str) -> User:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        raise Unauthorized("Invalid or expired token")
    user = db.get(User, int(payload["sub"]))
    if not user:
        raise Unauthorized("User no longer exists")
    return user


def set_role(db: Session, email: str, role: UserRole) -> User:
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if not user:
        raise NotFound("User not found")
    user.role = role
    db.commit()
    return user


# ── Authorization rules ──────────────────────────────────────────────────────

def ensure_can_manage_property(user: User, prop: Property) -> None:
    if user.role == UserRole.admin or (prop.owner_id is not None and prop.owner_id == user.id):
        return
    raise Forbidden("You can only manage your own listings")


def ensure_can_view_booking(user: User, booking: Booking, prop: Property) -> None:
    if user.role == UserRole.admin or booking.renter_id == user.id or prop.owner_id == user.id:
        return
    raise Forbidden("Not your booking")


def ensure_can_cancel_booking(user: User, booking: Booking, prop: Property) -> None:
    ensure_can_view_booking(user, booking, prop)


def ensure_signup_role(role: UserRole) -> None:
    if role == UserRole.admin:
        raise BadRequest("Admin accounts cannot be created through signup")
