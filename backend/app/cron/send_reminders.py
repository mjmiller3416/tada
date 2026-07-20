"""Standalone entrypoint for the Railway "cron" service. Deployed with a
Cron Schedule of `* * * * *` (every minute) and start command
`python -m app.cron.send_reminders`. Deliberately not a FastAPI route —
Railway invokes it as a one-shot process, not an HTTP request.

Phase 0: the Reminder table is expected to be empty (no feature builds
reminders yet), so this mainly proves the query -> push pipeline runs
end to end on schedule. Phase 1 wires real reminders into this table.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import SessionLocal
from app.models.push_subscription import PushSubscription
from app.models.reminder import Reminder
from app.services.push_service import send_push

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("cron.send_reminders")


def run() -> None:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        due = db.scalars(
            select(Reminder).where(Reminder.active.is_(True), Reminder.scheduled_for <= now)
        ).all()

        logger.info("Checked reminders at %s: %d due", now.isoformat(), len(due))

        for reminder in due:
            subscriptions = db.scalars(
                select(PushSubscription).where(PushSubscription.user_id == reminder.user_id)
            ).all()
            for subscription in subscriptions:
                send_push(subscription, title=reminder.title, body=reminder.body, db=db)

            reminder.last_sent_at = now
            if reminder.recurrence_rule is None:
                reminder.active = False

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    run()
