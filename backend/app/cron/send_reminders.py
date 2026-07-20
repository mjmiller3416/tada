"""Standalone entrypoint for the Railway "cron" service. Deployed with a
Cron Schedule of `* * * * *` (every minute) and start command
`python -m app.cron.send_reminders`. Deliberately not a FastAPI route —
Railway invokes it as a one-shot process, not an HTTP request.

Phase 1: the Reminder table now holds real rows (see
services/reminder_service.py):

- Daily nudges (recurrence_rule="daily", no task): the body is composed
  here at send time from the live priority ranking, and scheduled_for is
  advanced to the next local occurrence after sending.
- Snooze reminders (task_id set): one-shot "ready when you are" nudges.
  If the task got done (or deactivated) in the meantime, the reminder is
  dropped silently — never nag about finished work (SPEC §5, no guilt).
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.push_subscription import PushSubscription
from app.models.reminder import Reminder
from app.models.task import Task
from app.models.user import User
from app.services import reminder_service
from app.services.push_service import send_push

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("cron.send_reminders")


def _send_to_user(db: Session, user_id: int, title: str, body: str) -> int:
    """Push to every subscription (phone + Chromebook) the user has."""
    subscriptions = db.scalars(
        select(PushSubscription).where(PushSubscription.user_id == user_id)
    ).all()
    sent = 0
    for subscription in subscriptions:
        if send_push(subscription, title=title, body=body, db=db):
            sent += 1
    return sent


def _process(db: Session, reminder: Reminder, now: datetime) -> None:
    user = db.get(User, reminder.user_id)
    if user is None:
        reminder.active = False
        return

    if reminder.task_id is not None:
        # Snooze reminder: drop silently if the moment has passed.
        task = db.get(Task, reminder.task_id)
        if (
            task is None
            or not task.is_active
            or (task.last_done_at is not None and task.last_done_at >= reminder.created_at)
        ):
            reminder.active = False
            logger.info("Reminder %d dropped (task done or gone)", reminder.id)
            return
        _send_to_user(db, user.id, reminder.title, reminder.body)
        reminder.last_sent_at = now
        reminder.active = False
        return

    if reminder.recurrence_rule == reminder_service.DAILY_RULE:
        # Daily nudge: decay-aware content, then roll to tomorrow.
        title, body = reminder_service.compose_daily_nudge(db, user)
        _send_to_user(db, user.id, title, body)
        reminder.last_sent_at = now
        reminder_service.advance_daily_nudge(db, reminder, user)
        return

    # Plain one-shot reminder.
    _send_to_user(db, user.id, reminder.title, reminder.body)
    reminder.last_sent_at = now
    reminder.active = False


def run() -> None:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        due = db.scalars(
            select(Reminder).where(Reminder.active.is_(True), Reminder.scheduled_for <= now)
        ).all()

        logger.info("Checked reminders at %s: %d due", now.isoformat(), len(due))

        for reminder in due:
            _process(db, reminder, now)

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    run()
