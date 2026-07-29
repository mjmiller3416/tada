"""Per-user settings (SPEC §3 `Setting`): a small key/value store with
defaults, so features read one merged dict and unset keys just work."""

from datetime import date

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
