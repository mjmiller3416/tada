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

Phase 4 adds list countdowns (list_id set; packing countdowns before
Phase 6 generalized lists): "Trip in 3 days — 6 items still to pack",
composed here at send time from the live list so the count is never
stale, advanced daily until the event date. Same no-guilt rule: an
archived list or a passed date drops silently.

Delivery ordering (issue #24): each reminder's new state is COMMITTED
before its push goes out. `_process` only decides and mutates — it never
touches the network — and returns the pushes to deliver; `run` commits,
then delivers. A crash or push failure therefore can't roll back state
that already produced a notification (which used to re-push a poison
reminder every minute, forever). The trade: a crash in the narrow gap
between commit and send loses that one notification — the no-guilt
philosophy prefers a lost nudge over a nagging repeat.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.models.lists import List
from app.models.reminder import Reminder
from app.models.task import Task
from app.models.user import User
from app.services import lists as list_service
from app.services import reminder_service, settings_service
from app.services.push_service import DEFAULT_TTL, push_to_user

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("cron.send_reminders")

# Notifications sharing a tag replace each other on the device, so
# repeated daily nudges never stack up in the tray.
DAILY_NUDGE_TAG = "daily-nudge"
SESSION_TIMER_TAG = "session-timer"

#: A "that's your N minutes" alert is only meaningful right now — if her
#: phone can't be reached within a couple of minutes, let it expire
#: rather than congratulate her an hour after she stopped (issue #35).
SESSION_TIMER_TTL = 120

#: Postgres advisory lock key ("7ADA") so overlapping runs can never
#: double-send the same due reminders (issue #24). Railway skips
#: overlapping cron executions on its own; this covers manual runs and
#: any future scheduler that doesn't.
CRON_LOCK_KEY = 0x7ADA


@dataclass
class PushJob:
    """One notification to deliver after commit. Carries everything
    `_deliver` needs so it never has to touch reminder state."""

    reminder_id: int
    user_id: int
    user_name: str
    title: str
    body: str
    tag: str | None = None
    ttl: int = DEFAULT_TTL


def _user_tz(db: Session, user_id: int) -> ZoneInfo | timezone:
    try:
        return ZoneInfo(settings_service.get_setting(db, user_id, "timezone"))
    except Exception:
        return timezone.utc


def _end_of_day_ttl(tz: ZoneInfo | timezone) -> int:
    """Seconds until local midnight — a "Good morning" nudge has no
    business arriving tomorrow, but should survive a phone that dozes
    until she picks it up this afternoon (issue #35). Floor of a minute
    so a nudge composed at 23:59 still gets a moment to deliver."""
    now_local = datetime.now(tz)
    midnight = datetime.combine(
        now_local.date() + timedelta(days=1), time.min, tzinfo=tz
    )
    return max(60, int((midnight - now_local).total_seconds()))


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


def _process(db: Session, reminder: Reminder, now: datetime) -> list[PushJob]:
    """Decide what this due reminder means and mutate its state — send
    nothing. Returns the pushes to deliver once the caller has committed
    (see the module docstring on ordering)."""
    user = db.get(User, reminder.user_id)
    if user is None:
        reminder.active = False
        return []

    def job(title: str, body: str, tag: str | None = None, ttl: int = DEFAULT_TTL) -> list[PushJob]:
        return [PushJob(reminder.id, user.id, user.name, title, body, tag=tag, ttl=ttl)]

    # Session timer (Phase 5): a one-shot alert she asked for minutes
    # ago, so it fires even during a vacation window — it's her timer,
    # not a nudge. It only notifies; it never ends the session for her.
    if reminder_service.is_session_timer(reminder):
        reminder.last_sent_at = now
        reminder.active = False
        return job(reminder.title, reminder.body, tag=SESSION_TIMER_TAG, ttl=SESSION_TIMER_TTL)

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
        return []

    if reminder.list_id is not None:
        # List countdown (Phase 4): compose from the live list so the
        # unchecked count is current; drop silently if the list is
        # archived/gone or the event has passed — never nag after the
        # moment (SPEC §5, no guilt).
        parent_list = db.get(List, reminder.list_id)
        if parent_list is None or parent_list.status != "active":
            reminder.active = False
            logger.info("Reminder %d dropped (list archived or gone)", reminder.id)
            return []
        first_name = user.name.split()[0] if user.name else "there"
        composed = list_service.compose_countdown(parent_list, today, first_name)
        if composed is None:
            reminder.active = False
            logger.info("Reminder %d dropped (event date passed)", reminder.id)
            return []
        title, body = composed
        reminder.last_sent_at = now
        checked, total = list_service.progress(parent_list)
        if total and checked == total:
            # Everything's checked off — that cheerful send was the finale.
            reminder.active = False
        else:
            list_service.advance_countdown_reminder(db, reminder, parent_list, user)
        return job(title, body)

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
            return []
        reminder.last_sent_at = now
        reminder.active = False
        return job(reminder.title, reminder.body)

    if reminder.recurrence_rule == reminder_service.DAILY_RULE:
        # Daily nudge: decay-aware content, then roll to tomorrow.
        title, body = reminder_service.compose_daily_nudge(db, user)
        reminder.last_sent_at = now
        reminder_service.advance_daily_nudge(db, reminder, user)
        return job(
            title,
            body,
            tag=DAILY_NUDGE_TAG,
            ttl=_end_of_day_ttl(_user_tz(db, user.id)),
        )

    # Plain one-shot reminder.
    reminder.last_sent_at = now
    reminder.active = False
    return job(reminder.title, reminder.body)


def _deliver(db: Session, push: PushJob) -> None:
    """Post-commit delivery. Every successful send gets a log line to
    mirror the drop lines — silence here has turned diagnoses into
    guesswork. Never raises into the main loop: the reminder's state is
    already committed, so the only sane response to a failure is to log
    it and move on."""
    try:
        sent = push_to_user(
            db, push.user_id, push.title, push.body, tag=push.tag, ttl=push.ttl
        )
        logger.info(
            "Reminder %d sent to user %d (%s): %d push(es) delivered",
            push.reminder_id,
            push.user_id,
            push.user_name,
            sent,
        )
    except Exception:
        logger.exception(
            "Reminder %d: delivery failed for user %d", push.reminder_id, push.user_id
        )
        db.rollback()  # leave the session clean for the next reminder


def run() -> None:
    # The advisory lock needs its own connection for the whole run — the
    # session's connection goes back to the pool at every commit, and a
    # session-level lock must outlive all of them. Postgres only; local
    # SQLite dev runs are single-shot anyway.
    lock_conn = engine.connect() if engine.dialect.name == "postgresql" else None
    if lock_conn is not None:
        locked = lock_conn.exec_driver_sql(
            "SELECT pg_try_advisory_lock(%s)", (CRON_LOCK_KEY,)
        ).scalar()
        if not locked:
            logger.info("Another run holds the cron lock; skipping this one")
            lock_conn.close()
            return

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
            # broken state for the reminders after it. Pushes go out
            # only after their commit succeeds (module docstring).
            try:
                jobs = _process(db, reminder, now)
                db.commit()
            except Exception:
                logger.exception(
                    "Reminder %d failed; continuing with the rest", reminder.id
                )
                db.rollback()
                continue
            for push in jobs:
                _deliver(db, push)
    finally:
        db.close()
        if lock_conn is not None:
            try:
                lock_conn.exec_driver_sql(
                    "SELECT pg_advisory_unlock(%s)", (CRON_LOCK_KEY,)
                )
            finally:
                lock_conn.close()


if __name__ == "__main__":
    run()
