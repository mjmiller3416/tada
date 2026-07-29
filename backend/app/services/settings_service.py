"""Per-user settings (SPEC §3 `Setting`): a small key/value store with
defaults, so features read one merged dict and unset keys just work."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.setting import Setting

#: Every known setting and its default. Values are stored as strings;
#: the API schema owns validation/typing. Booleans store as "true"/"false".
DEFAULTS: dict[str, str] = {
    "daily_focus_count": "3",        # top-N on the home screen (1..3)
    "default_session_minutes": "15",  # the "I have X minutes" default
    "daily_nudge_time": "08:30",     # local HH:MM; "" disables the nudge
    "timezone": "America/New_York",  # IANA name, for the nudge schedule
    # Phase 3 overlays — opt-in, off by default (SPEC §6). Toggling one
    # off cleanly returns to the core decay-driven experience.
    "zones_enabled": "false",        # the FlyLady zone overlay
    "campaigns_enabled": "false",    # seasonal campaigns
    # Vacation mode (Phase 4.6): pause the nudges, keep the decay
    # running. The user's local date (YYYY-MM-DD) of the LAST paused
    # day; "" = not away. Reminders resume by themselves the day after.
    "vacation_until": "",
    # Internal (Phase 5, never exposed through the settings API): when
    # "I'm back" ends a vacation early, vacation_until is cleared — but
    # the days already spent away must stay neutral for the streak
    # freeze. This records the last day of that elapsed window so the
    # streak logic can still excuse it.
    "streak_frozen_until": "",
}


def get_settings(db: Session, user_id: int) -> dict[str, str]:
    """The user's settings merged over the defaults."""
    rows = db.scalars(select(Setting).where(Setting.user_id == user_id)).all()
    merged = dict(DEFAULTS)
    for row in rows:
        if row.key in DEFAULTS:
            merged[row.key] = row.value
    return merged


def get_setting(db: Session, user_id: int, key: str) -> str:
    return get_settings(db, user_id)[key]


def set_settings(db: Session, user_id: int, updates: dict[str, str]) -> dict[str, str]:
    """Upsert the given keys for the user. Caller commits."""
    rows = {
        row.key: row
        for row in db.scalars(select(Setting).where(Setting.user_id == user_id)).all()
    }
    for key, value in updates.items():
        if key not in DEFAULTS:
            continue
        if key in rows:
            rows[key].value = value
        else:
            db.add(Setting(user_id=user_id, key=key, value=value))
    # The session runs with autoflush=False — flush so the merged read
    # below (and any nudge sync that follows) sees the new values.
    db.flush()
    return get_settings(db, user_id)


def vacation_until(db: Session, user_id: int) -> date | None:
    """The last day of the user's vacation window (her local calendar),
    or None when vacation mode is off. Phase 5 will freeze streaks
    across this same window — read it through here, not the raw key."""
    raw = get_setting(db, user_id, "vacation_until").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def is_on_vacation(db: Session, user_id: int, today: date) -> bool:
    """Whether `today` (the user's LOCAL date) falls inside the vacation
    window. This pauses reminder dispatch only — the decay engine in
    services/scheduling.py must never consult it (SPEC §4: she'd rather
    come home to an honest picture than a fiction)."""
    until = vacation_until(db, user_id)
    return until is not None and today <= until


def _parse_date(raw: str) -> date | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def record_vacation_clear(db: Session, user_id: int, local_today: date) -> None:
    """Called just before "I'm back" clears vacation_until. The days
    already spent away become part of the streak freeze — ending a trip
    early must never turn it into a streak break (Phase 5). Caller
    commits."""
    until = vacation_until(db, user_id)
    if until is None:
        return
    # The elapsed window ends yesterday (today she's back and cleaning
    # counts again), or at the planned end if that already passed.
    frozen_through = min(until, local_today - timedelta(days=1))
    previous = _parse_date(get_setting(db, user_id, "streak_frozen_until"))
    if previous is None or frozen_through > previous:
        set_settings(db, user_id, {"streak_frozen_until": frozen_through.isoformat()})


def streak_freeze_until(db: Session, user_id: int) -> date | None:
    """The last local day the streak logic should treat as neutral —
    vacation days are not a break to make up, and not credit either
    (Phase 5). Covers both a window that ran its course (vacation_until
    keeps its past date) and one ended early ("I'm back" records the
    elapsed part via record_vacation_clear). Streak code reads the
    freeze through here, never the raw keys."""
    values = get_settings(db, user_id)
    candidates = [
        d
        for d in (
            _parse_date(values["vacation_until"]),
            _parse_date(values["streak_frozen_until"]),
        )
        if d is not None
    ]
    return max(candidates) if candidates else None
