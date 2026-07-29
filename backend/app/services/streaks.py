"""Streak tracking (SPEC §5: forgiving streaks, never punishing).

Wired into scheduling.complete_task() — every completion runs through
here. The rules, in her local calendar (never UTC):

- Completing again on an already-counted day changes nothing.
- Consecutive days grow the streak by one.
- One missed day is forgiven (the SPEC §5 grace day): the streak still
  grows by one — the missed day itself earns no credit.
- Two or more missed days quietly start a new streak at 1. A broken
  streak is never announced, never explained, never apologised for —
  the UI only ever shows the current number.
- Vacation days (Phase 4.6's window) are neutral: not a break to make
  up, and not credit either. Back from eight days away, her streak
  reads exactly what it did when she left. She asked for this
  explicitly.
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.user import User
from app.services import settings_service

#: A gap of up to this many calendar days still grows the streak — 1 is
#: simply "the next day", 2 is the one forgiven grace day (SPEC §5).
GRACE_GAP_DAYS = 2


def _local_date(db: Session, user_id: int, now: datetime) -> date:
    """`now` as the user's local calendar day. A "day" for streaks means
    her day, so the streak flips at her midnight, not UTC's."""
    tz_name = settings_service.get_setting(db, user_id, "timezone")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    return now.astimezone(tz).date()


def _frozen_days_between(start: date, end: date, freeze_until: date | None) -> int:
    """How many days strictly between `start` and `end` fall inside the
    streak freeze (i.e. are on/before `freeze_until`). Those days are
    neutral and drop out of the gap entirely."""
    if freeze_until is None:
        return 0
    last_frozen = min(end - timedelta(days=1), freeze_until)
    return max(0, (last_frozen - start).days)


def update_streak(db: Session, user: User, now: datetime | None = None) -> None:
    """Advance the user's streak for a completion happening at `now`.
    Idempotent within a day; caller commits.

    A completion during the vacation window itself changes nothing —
    vacation days earn no credit and cost nothing, so the streak still
    reads exactly what it did when she left."""
    now = now or datetime.now(timezone.utc)
    today = _local_date(db, user.id, now)

    if settings_service.is_on_vacation(db, user.id, today):
        return

    if user.last_active_date is None:
        user.current_streak = 1
    else:
        gap = (today - user.last_active_date).days
        if gap <= 0:
            return  # today is already counted
        freeze_until = settings_service.streak_freeze_until(db, user.id)
        effective_gap = gap - _frozen_days_between(
            user.last_active_date, today, freeze_until
        )
        if effective_gap <= GRACE_GAP_DAYS:
            user.current_streak += 1
        else:
            user.current_streak = 1  # quietly; the UI never remarks on it

    user.last_active_date = today
    user.longest_streak = max(user.longest_streak, user.current_streak)
