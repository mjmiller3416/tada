"""One-off script: creates or updates the single owner User (SPEC §2 —
only the owner logs in during Phase 1, but kid logins reuse this same
User model in Phase 2).

Run locally against the target DATABASE_URL (e.g. via `railway run` against
the Railway Postgres, or with a local .env pointing at it):

    OWNER_NAME="..." OWNER_EMAIL="..." OWNER_PIN="1234" python -m scripts.seed_owner

Re-running with the same OWNER_EMAIL updates that user's name/PIN rather
than creating a duplicate.
"""

import os
import sys

from sqlalchemy import select

from app.database import SessionLocal
from app.models.user import User
from app.services.auth_service import hash_pin


def main() -> None:
    name = os.environ.get("OWNER_NAME")
    email = os.environ.get("OWNER_EMAIL")
    pin = os.environ.get("OWNER_PIN")

    if not name or not email or not pin:
        print(
            "Set OWNER_NAME, OWNER_EMAIL, and OWNER_PIN env vars before running this script.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(name=name, email=email, role="owner", password_hash=hash_pin(pin))
            db.add(user)
            action = "Created"
        else:
            user.name = name
            user.password_hash = hash_pin(pin)
            action = "Updated"

        db.commit()
        print(f"{action} owner user '{name}' <{email}>.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
