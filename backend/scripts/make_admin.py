"""Promote an existing user to admin. Admins cannot be created through signup.

    python -m scripts.make_admin someone@example.com
"""
import sys

from database import SessionLocal
from models import UserRole
from services.users import set_role


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    db = SessionLocal()
    try:
        user = set_role(db, sys.argv[1], UserRole.admin)
        print(f"{user.email} is now an admin")
    finally:
        db.close()


if __name__ == "__main__":
    main()
