"""Reminder building (SPEC §6 "Reminders" + decay-aware snooze).

Two reminder kinds get written to the table the Phase 0 cron polls:

- **The daily nudge** — one recurring row per user (`recurrence_rule =
  "daily"`, no task). `sync_daily_nudge` keeps it aligned with the user's
  `daily_nudge_time` / `timezone` settings; the cron composes its body at
  send time (decay-aware) and advances `scheduled_for`.
- **Snooze reminders** — one-shot rows tied to a task, created when she
  snoozes ("remind me later"). The cron drops them silently if the task
  got done in the meantime — never nag about finished work.
- **Session timers** (Phase 5) — one-shot "that's your N minutes" rows,
  routed through this same table + cron on purpose: a JS timer dies
  when the screen sleeps, and she cleans with the phone in her pocket.
  Marked via recurrence_rule = "session_timer:<total minutes>" so no
  schema change is needed; the alert always reads as a win, never as a
  failure to finish, and it never ends her session — she decides.

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

#: recurrence_rule prefix for session timers: "session_timer:<total
#: minutes>". The total rides along so extending can recompose the
#: congratulations with the right number — no new column needed.
SESSION_TIMER_PREFIX = "session_timer:"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def is_session_timer(reminder: Reminder) -> bool:
    return (reminder.recurrence_rule or "").startswith(SESSION_TIMER_PREFIX)


def _timer_copy(total_minutes: int) -> tuple[str, str]:
    """The time's-up alert. She asked for a congratulations here — it
    reads as a win, never "time's up, you failed to finish"."""
    return (
        f"That's {total_minutes} minutes — look at what you got done 🎉",
        "Every one of those minutes counts. Keep going if you're in the "
        "groove, or call it a lovely win — your call, always.",
    )


def start_session_timer(db: Session, user: User, minutes: int) -> Reminder:
    """Create the one-shot timer for a timed session, replacing any
    earlier still-pending timer (one session at a time). Caller commits."""
    for row in db.scalars(
        select(Reminder).where(
            Reminder.user_id == user.id,
            Reminder.recurrence_rule.like(f"{SESSION_TIMER_PREFIX}%"),
            Reminder.active.is_(True),
        )
    ).all():
        row.active = False

    title, body = _timer_copy(minutes)
    reminder = Reminder(
        user_id=user.id,
        title=title,
        body=body,
        scheduled_for=_utcnow() + timedelta(minutes=minutes),
        recurrence_rule=f"{SESSION_TIMER_PREFIX}{minutes}",
        active=True,
    )
    db.add(reminder)
    db.flush()
    return reminder


def extend_session_timer(db: Session, reminder: Reminder, minutes: int) -> Reminder:
    """"Extend" adds more time: push the alert out by `minutes` (from now,
    if it already fired) and recompose the congratulations for the new
    total. The queue top-up happens in the session flow — extending never
    leaves her with time and nothing to do. Caller commits."""
    now = _utcnow()
    scheduled = reminder.scheduled_for
    if scheduled.tzinfo is None:
        scheduled = scheduled.replace(tzinfo=timezone.utc)
    base = max(scheduled, now) if reminder.active else now
    reminder.scheduled_for = base + timedelta(minutes=minutes)

    previous_total = int(reminder.recurrence_rule.removeprefix(SESSION_TIMER_PREFIX))
    total = previous_total + minutes
    reminder.recurrence_rule = f"{SESSION_TIMER_PREFIX}{total}"
    reminder.title, reminder.body = _timer_copy(total)
    reminder.active = True
    reminder.last_sent_at = None
    return reminder


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
    top = scheduling.daily_focus(db, limit=1, for_user_id=user.id)
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
