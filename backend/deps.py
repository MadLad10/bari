"""FastAPI dependencies for authentication and role checks."""
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from database import get_db
from models import User, UserRole
from services.errors import Forbidden
from services.users import Unauthorized, user_from_token

_bearer = HTTPBearer(auto_error=False)


def get_current_user_optional(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    if creds is None:
        return None
    return user_from_token(db, creds.credentials)


def get_current_user(user: User | None = Depends(get_current_user_optional)) -> User:
    if user is None:
        raise Unauthorized("Login required")
    return user


def require_role(*roles: UserRole):
    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles and user.role != UserRole.admin:
            raise Forbidden(f"Requires role: {', '.join(r.value for r in roles)}")
        return user
    return _dep
