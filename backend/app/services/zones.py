"""The FlyLady zone overlay (SPEC §6; Phase 3, corrected in 10–11).

An opt-in layer on top of the decay engine — never a replacement. The
home is divided into five zones, each getting one focused week per
month. Since the scheduling lanes (SPEC §4), a zone is an ELIGIBILITY
WINDOW for task_type="zone" missions — "this week's zone" is derived
from today's date in her timezone and gates which missions are askable.
The decay engine keeps driving everyday upkeep underneath, everywhere,
regardless of the active zone.
"""

import calendar
from datetime import date, datetime, tzinfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.room import Room
from app.models.zone import Zone
from app.services import settings_service

#: FlyLady's five zones (SPEC §6) — the seed defaults. Fully editable:
#: the names can be changed and rooms remapped in Settings, so "most
#: homes differ" is a rename away.
DEFAULT_ZONES: list[dict] = [
    {"name": "Entrance, porch & dining room", "week_of_month": 1, "sort_order": 1},
    {"name": "Kitchen", "week_of_month": 2, "sort_order": 2},
    {"name": "Bathroom & one extra room", "week_of_month": 3, "sort_order": 3},
    {"name": "Master bedroom, bath & closet", "week_of_month": 4, "sort_order": 4},
    {"name": "Living & family room", "week_of_month": 5, "sort_order": 5},
]

#: Room-name keywords → default zone week, used to auto-map the rooms
#: she already has when the overlay is first enabled. Checked in order;
#: first hit wins. Anything unmatched is left unzoned for her to place.
_AUTO_MAP: list[tuple[tuple[str, ...], int]] = [
    (("entry", "entrance", "foyer", "porch", "dining", "hall"), 1),
    (("kitchen", "pantry"), 2),
    (("bath", "laundry", "office", "playroom"), 3),
    (("bed", "master", "closet", "nursery"), 4),
    (("living", "family", "den", "lounge"), 5),
]


def local_today(db: Session, user_id: int) -> date:
    """Today in the owner's timezone (a Settings value) — zone weeks and
    campaign windows should flip at her midnight, not UTC's."""
    return datetime.now(settings_service.user_timezone(db, user_id)).date()


#: How many of the month's final days clamp to week 5 when the raw
#: Monday-week arithmetic never reaches it (issue #21) — zone 5's "the
#: last few days", mirroring zone 1's "the first few days".
ZONE_5_MIN_DAYS = 3


def week_of_month(today: date) -> int:
    """Which FlyLady week this date falls in, 1..5.

    Weeks run Monday–Sunday. A partial week at the start of the month
    counts as week 1 — FlyLady's "the first few days of the month" —
    and anything past the fourth week clamps to 5, so the month's last
    few days always belong to zone 5 (zones 1 and 5 often share a
    calendar week, per SPEC §6).

    One month shape defeats the raw arithmetic: a 28-day February that
    starts on a Monday packs into exactly four Monday–Sunday weeks, so
    no day ever reaches week 5 and zone 5 would silently skip the month
    (issue #21). When that happens, the month's last ZONE_5_MIN_DAYS
    days clamp to week 5 — every other month shape already ends in week
    5 naturally and is left byte-identical."""
    first_weekday = today.replace(day=1).weekday()  # Monday = 0
    week = (today.day + first_weekday - 1) // 7 + 1
    last_day = calendar.monthrange(today.year, today.month)[1]
    last_week = (last_day + first_weekday - 1) // 7 + 1
    if last_week < 5 and today.day > last_day - ZONE_5_MIN_DAYS:
        return 5
    return min(week, 5)


def current_zone(db: Session, today: date) -> Zone | None:
    """The zone whose week contains today, or None if zones aren't set
    up (overlay never seeded)."""
    week = week_of_month(today)
    return db.scalar(select(Zone).where(Zone.week_of_month == week))


def zone_for_moment(db: Session, now: datetime, tz: tzinfo) -> Zone | None:
    """The zone whose week contains `now` in the given timezone — the
    backend-derived "current zone" the Phase 10 zone lane selects by.
    Injectable now/tz (unlike local_today, which reads the clock) so the
    her-midnight-not-UTC boundary is directly testable: the zone must
    flip when HER day does."""
    return current_zone(db, now.astimezone(tz).date())


def seed_default_zones(db: Session) -> list[Zone]:
    """Create the five FlyLady zones if none exist, then auto-map any
    still-unzoned rooms by name. Idempotent: re-running never duplicates
    zones and never touches a room she has already placed (or moved).
    Caller commits."""
    zones = list(db.scalars(select(Zone).order_by(Zone.week_of_month)).all())
    if not zones:
        zones = [Zone(**fields) for fields in DEFAULT_ZONES]
        db.add_all(zones)
        db.flush()  # assign ids before rooms point at them

    by_week = {zone.week_of_month: zone for zone in zones}
    unzoned = db.scalars(select(Room).where(Room.zone_id.is_(None))).all()
    for room in unzoned:
        name = room.name.lower()
        for keywords, week in _AUTO_MAP:
            if any(keyword in name for keyword in keywords) and week in by_week:
                room.zone_id = by_week[week].id
                break
    return zones
