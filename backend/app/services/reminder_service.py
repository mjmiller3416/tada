"""Reminder building (SPEC §6 "Reminders" + decay-aware snooze).

Two reminder kinds get written to the table the Phase 0 cron polls:

- **The daily nudge** — one recurring row per user (`recurrence_rule =
  "daily"`, no task). `sync_daily_nudge` keeps it aligned with the user's
  `daily_nudge_time` / `timezone` settings; the cron composes its body at
  send time (decay-aware) and advances `scheduled_for`.
- **Snooze reminders** — one-shot rows tied to a task, created when she
  snoozes ("remind me later"). The cron drops them silently if the task
  got done in the meantime — never nag about finished work.

All copy here follows the no-guilt voice (SPEC §5): warm, first-name,
zero pressure.
"""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.reminder import Reminder
from app.models.task import Task
from app.models.user import User
from app.services import scheduling, settings_service

DAILY_RULE = "daily"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def next_nudge_occurrence(nudge_time: str, tz_name: str, after: datetime) -> datetime:
    """The next moment (UTC) that local wall-clock `nudge_time` (HH:MM in
    `tz_name`) occurs strictly after `after`. DST is handled by computing
    in local wall-clock time and converting."""
    tz = ZoneInfo(tz_name)
    hour, minute = (int(part) for part in nudge_time.split(":"))
    local_after = after.astimezone(tz)
    candidate = datetime.combine(local_after.date(), time(hour, minute), tzinfo=tz)
    if candidate <= local_after:
        candidate = datetime.combine(
            local_after.date() + timedelta(days=1), time(hour, minute), tzinfo=tz
        )
    return candidate.astimezone(timezone.utc)


def _get_daily_nudge(db: Session, user_id: int) -> Reminder | None:
    return db.scalar(
        select(Reminder).where(
            Reminder.user_id == user_id,
            Reminder.recurrence_rule == DAILY_RULE,
            Reminder.task_id.is_(None),
        )
    )


def sync_daily_nudge(db: Session, user: User) -> None:
    """Create/update/disable the user's daily nudge row to match her
    settings. Called whenever settings change (and after onboarding).
    Caller commits."""
    settings = settings_service.get_settings(db, user.id)
    nudge_time = settings["daily_nudge_time"].strip()
    reminder = _get_daily_nudge(db, user.id)

    if not nudge_time:
        if reminder is not None:
            reminder.active = False
        return

    scheduled_for = next_nudge_occurrence(nudge_time, settings["timezone"], _utcnow())
    if reminder is None:
        db.add(
            Reminder(
                user_id=user.id,
                title="Good morning ☀️",
                body="",  # composed decay-aware at send time
                scheduled_for=scheduled_for,
                recurrence_rule=DAILY_RULE,
                active=True,
            )
        )
    else:
        reminder.scheduled_for = scheduled_for
        reminder.active = True
        reminder.last_sent_at = None


def advance_daily_nudge(db: Session, reminder: Reminder, user: User) -> None:
    """After the cron sends a daily nudge, move it to the next occurrence
    per the user's current settings. Caller commits."""
    settings = settings_service.get_settings(db, user.id)
    nudge_time = settings["daily_nudge_time"].strip()
    if not nudge_time:
        reminder.active = False
        return
    reminder.scheduled_for = next_nudge_occurrence(
        nudge_time, settings["timezone"], _utcnow()
    )


def compose_daily_nudge(db: Session, user: User) -> tuple[str, str]:
    """The nudge content, composed at send time from the live priority
    ranking so it always reflects today's actual state."""
    first_name = user.name.split()[0] if user.name else "there"
    top = scheduling.daily_focus(db, limit=1)
    if not top:
        return (
            f"Good morning, {first_name} ☀️",
            "Your home's in good shape — nothing pressing today. Enjoy it ✨",
        )
    task = top[0]
    where = f" in the {task.room.name.lower()}" if task.room else ""
    return (
        f"Good morning, {first_name} ☀️",
        f"One small win when you're ready: {task.name}{where} "
        f"(about {task.estimated_minutes} min). That's all it takes.",
    )


def create_snooze_reminder(
    db: Session, user: User, task: Task, when: datetime
) -> None:
    """A one-shot "remind me later" row for a snoozed task. Replaces any
    earlier pending snooze reminder for the same task so she's never
    double-nudged. Caller commits."""
    existing = db.scalars(
        select(Reminder).where(
            Reminder.user_id == user.id,
            Reminder.task_id == task.id,
            Reminder.active.is_(True),
        )
    ).all()
    for row in existing:
        row.active = False

    db.add(
        Reminder(
            user_id=user.id,
            task_id=task.id,
            title="Ready when you are 💛",
            body=f"{task.name} is back on the list — no rush "
            f"(about {task.estimated_minutes} min).",
            scheduled_for=when,
            active=True,
        )
    )


def clear_task_reminders(db: Session, task_id: int) -> None:
    """Deactivate pending reminders for a task (used on wake/complete so
    a stale 'later' nudge never fires after the moment passed). Caller
    commits."""
    rows = db.scalars(
        select(Reminder).where(Reminder.task_id == task_id, Reminder.active.is_(True))
    ).all()
    for row in rows:
        row.active = False
