"""Manually push a custom notification to a user's devices.

A local convenience wrapper around services/push_service.push_to_user —
never deployed, never scheduled. Run from backend/ with the Railway env
injected so DATABASE_URL and the VAPID keys are present:

    python -m scripts.send_note --user "Maryann" "Title" "Body text"

The recipient is always explicit — the household has two owners, so there
is no safe default. Prefer the scripts/send-note.ps1 wrapper, which pulls
the Railway credentials for you.
"""

import argparse

from sqlalchemy import select

from app.database import SessionLocal
from app.models.user import User
from app.services.push_service import push_to_user


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a custom push notification")
    parser.add_argument("title", help="Notification title")
    parser.add_argument("body", help="Notification body text")
    parser.add_argument("--user", required=True, help="Recipient's name")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        user = db.scalars(select(User).where(User.name.ilike(args.user))).first()
        if user is None:
            raise SystemExit(f"No user named {args.user!r} found")
        sent = push_to_user(db, user.id, args.title, args.body)
        print(f"Sent to {user.name}: {sent} device(s) reached")
    finally:
        db.close()


if __name__ == "__main__":
    main()
