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

Phase 4 adds packing countdowns (packing_list_id set): "Trip in 3 days —
6 items still unpacked", composed here at send time from the live list
so the count is never stale, advanced daily until the event date. Same
no-guilt rule: an archived list or a passed date drops silently.
"""

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.packing import PackingList
from app.models.reminder import Reminder
from app.models.task import Task
from app.models.user import User
from app.services import packing as packing_service
from app.services import reminder_service, settings_service
from app.services.push_service import push_to_user

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("cron.send_reminders")

# Notifications sharing a tag replace each other on the device, so
# repeated daily nudges never stack up in the tray.
DAILY_NUDGE_TAG = "daily-nudge"
SESSION_TIMER_TAG = "session-timer"


def _send(
    db: Session,
    reminder: Reminder,
    user: User,
    title: str,
    body: str,
    tag: str | None = None,
) -> None:
    """Push and log. Every successful send gets a log line to mirror the
    drop lines — silence here has turned diagnoses into guesswork."""
    sent = push_to_user(db, user.id, title, body, tag=tag)
    logger.info(
        "Reminder %d sent to user %d (%s): %d push(es) delivered",
        reminder.id,
        user.id,
        user.name,
        sent,
    )


def _user_tz(db: Session, user_id: int) -> ZoneInfo | timezone:
    try:
        return ZoneInfo(settings_service.get_setting(db, user_id, "timezone"))
    except Exception:
        return timezone.utc


def _defer_for_vacation(db: Session, reminder: Reminder, user: User, now: datetime) -> None:
    """Vacation skip (Phase 4.6): push the reminder past today WITHOUT
    deactivating it, so everything resumes by itself. The daily nudge
    rolls forward through its own service (respecting her nudge time);
    everything else keeps its wall-clock time and slides a day at a time
    — so nothing fires at an odd hour the moment the window closes, and
    an early "I'm back" is never more than a day from normal service."""
    if reminder.recurrence_rule == reminder_service.DAILY_RULE:
        reminder_service.advance_daily_nudge(db, reminder, user)
        return
    next_at = reminder.scheduled_for
    if next_at.tzinfo is None:
        next_at = next_at.replace(tzinfo=timezone.utc)
    while next_at <= now:
        next_at += timedelta(days=1)
    reminder.scheduled_for = next_at


def _process(db: Session, reminder: Reminder, now: datetime) -> None:
    user = db.get(User, reminder.user_id)
    if user is None:
        reminder.active = False
        return

    # Session timer (Phase 5): a one-shot alert she asked for minutes
    # ago, so it fires even during a vacation window — it's her timer,
    # not a nudge. It only notifies; it never ends the session for her.
    if reminder_service.is_session_timer(reminder):
        _send(db, reminder, user, reminder.title, reminder.body, tag=SESSION_TIMER_TAG)
        reminder.last_sent_at = now
        reminder.active = False
        return

    # Vacation mode (Phase 4.6): pause the nudges, keep the decay
    # running. ALL reminder types are skipped — never deactivated —
    # while the user's local today sits inside the window. Decay and
    # ranking (services/scheduling.py) are deliberately untouched.
    today = datetime.now(_user_tz(db, user.id)).date()
    if settings_service.is_on_vacation(db, user.id, today):
        _defer_for_vacation(db, reminder, user, now)
        logger.info(
            "Reminder %d skipped (user %d on vacation, resumes after %s)",
            reminder.id,
            user.id,
            settings_service.vacation_until(db, user.id),
        )
        return

    if reminder.packing_list_id is not None:
        # Packing countdown (Phase 4): compose from the live list so the
        # unpacked count is current; drop silently if the list is
        # archived/gone or the event has passed — never nag after the
        # moment (SPEC §5, no guilt).
        packing_list = db.get(PackingList, reminder.packing_list_id)
        if packing_list is None or packing_list.status != "active":
            reminder.active = False
            logger.info("Reminder %d dropped (packing list archived or gone)", reminder.id)
            return
        first_name = user.name.split()[0] if user.name else "there"
        composed = packing_service.compose_countdown(packing_list, today, first_name)
        if composed is None:
            reminder.active = False
            logger.info("Reminder %d dropped (event date passed)", reminder.id)
            return
        title, body = composed
        _send(db, reminder, user, title, body)
        reminder.last_sent_at = now
        packed, total = packing_service.progress(packing_list)
        if total and packed == total:
            # She's fully packed — that cheerful send was the finale.
            reminder.active = False
        else:
            packing_service.advance_countdown_reminder(db, reminder, packing_list, user)
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
        _send(db, reminder, user, reminder.title, reminder.body)
        reminder.last_sent_at = now
        reminder.active = False
        return

    if reminder.recurrence_rule == reminder_service.DAILY_RULE:
        # Daily nudge: decay-aware content, then roll to tomorrow.
        title, body = reminder_service.compose_daily_nudge(db, user)
        _send(db, reminder, user, title, body, tag=DAILY_NUDGE_TAG)
        reminder.last_sent_at = now
        reminder_service.advance_daily_nudge(db, reminder, user)
        return

    # Plain one-shot reminder.
    _send(db, reminder, user, reminder.title, reminder.body)
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
            # One bad reminder must never silence the rest of the run.
            # Each reminder commits on its own so a failure rolls back
            # only its own changes — and can't leave the session in a
            # broken state for the reminders after it.
            try:
                _process(db, reminder, now)
                db.commit()
            except Exception:
                logger.exception(
                    "Reminder %d failed; continuing with the rest", reminder.id
                )
                db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    run()
