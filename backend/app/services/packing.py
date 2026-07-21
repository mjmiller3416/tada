"""Packing lists (Phase 4) — a self-contained module, deliberately apart
from the cleaning core.

Packing is one-off and event-driven: no decay, no cadence, no
last_done_at, and nothing here touches services/scheduling.py or the
focus-session flow. It's also the one place a full grouped checklist
beats one-at-a-time — you want the whole list visible so nothing is
forgotten.

What it reuses so it feels native: the design system (frontend) and the
existing Reminder + Web Push plumbing, via an optional countdown nudge
tied to a list's event date ("Trip in 3 days — 6 items still unpacked").
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.packing import PackingItem, PackingList, PackingSection
from app.models.reminder import Reminder
from app.models.user import User
from app.services import settings_service
from app.services.packing_templates import TEMPLATES

#: recurrence_rule marker for packing countdown reminders — the cron
#: recognizes them by packing_list_id, this just keeps rows readable.
COUNTDOWN_RULE = "packing_countdown"

#: Default lead time for the countdown nudge when none is given.
DEFAULT_REMINDER_DAYS_BEFORE = 3


# ---------------------------------------------------------------------------
# Templates & cloning
# ---------------------------------------------------------------------------

def seed_templates(db: Session) -> None:
    """Create the ten starter templates (packing_templates.py) if none
    exist yet. Idempotent: once any template row is present this is a
    no-op, so her edits to templates are never overwritten. Caller
    commits."""
    existing = db.scalar(
        select(PackingList.id).where(PackingList.is_template.is_(True)).limit(1)
    )
    if existing is not None:
        return

    for category, name, sections in TEMPLATES:
        template = PackingList(name=name, category=category, is_template=True)
        template.sections = [
            PackingSection(
                name=section_name,
                sort_order=section_index,
                items=[
                    PackingItem(name=item_name, sort_order=item_index)
                    for item_index, item_name in enumerate(item_names)
                ],
            )
            for section_index, (section_name, item_names) in enumerate(sections)
        ]
        db.add(template)
    db.flush()


def clone_list(
    db: Session,
    source: PackingList,
    name: str,
    event_date: date | None,
) -> PackingList:
    """Clone any list — a template or an archived one, the same move —
    into a fresh active list: same sections and items, every checkbox
    cleared. Caller commits."""
    new_list = PackingList(
        name=name,
        category=source.category,
        is_template=False,
        event_date=event_date,
        status="active",
    )
    new_list.sections = [
        PackingSection(
            name=section.name,
            sort_order=section.sort_order,
            items=[
                PackingItem(
                    name=item.name,
                    quantity=item.quantity,
                    notes=item.notes,
                    packed=False,
                    sort_order=item.sort_order,
                )
                for item in section.items
            ],
        )
        for section in source.sections
    ]
    db.add(new_list)
    db.flush()
    return new_list


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------

def progress(packing_list: PackingList) -> tuple[int, int]:
    """(packed, total) across every section of the list."""
    items = [item for section in packing_list.sections for item in section.items]
    return sum(1 for item in items if item.packed), len(items)


def section_progress(section: PackingSection) -> tuple[int, int]:
    """(packed, total) for one section."""
    return sum(1 for item in section.items if item.packed), len(section.items)


# ---------------------------------------------------------------------------
# Reordering
# ---------------------------------------------------------------------------

def _reindex(rows: list, moving, new_index: int) -> None:
    """Drop `moving` at `new_index` (clamped) and renumber sort_order
    0..n-1 — treating sort_order as a target position keeps reordering a
    single PATCH instead of a client-side swap dance."""
    rows = [row for row in rows if row is not moving]
    rows.insert(max(0, min(new_index, len(rows))), moving)
    for index, row in enumerate(rows):
        row.sort_order = index


def move_section(db: Session, section: PackingSection, new_index: int) -> None:
    """Reposition a section within its list. Caller commits."""
    siblings = list(
        db.scalars(
            select(PackingSection)
            .where(PackingSection.list_id == section.list_id)
            .order_by(PackingSection.sort_order, PackingSection.id)
        ).all()
    )
    _reindex(siblings, section, new_index)


def move_item(db: Session, item: PackingItem, new_index: int) -> None:
    """Reposition an item within its section. Caller commits."""
    siblings = list(
        db.scalars(
            select(PackingItem)
            .where(PackingItem.section_id == item.section_id)
            .order_by(PackingItem.sort_order, PackingItem.id)
        ).all()
    )
    _reindex(siblings, item, new_index)


# ---------------------------------------------------------------------------
# The countdown reminder (reuses the Phase 0/1 Reminder + push plumbing)
# ---------------------------------------------------------------------------

def _get_countdown(db: Session, list_id: int) -> Reminder | None:
    return db.scalar(
        select(Reminder).where(
            Reminder.packing_list_id == list_id, Reminder.active.is_(True)
        )
    )


def reminder_enabled(db: Session, packing_list: PackingList) -> bool:
    """Whether a live countdown reminder exists for this list."""
    return _get_countdown(db, packing_list.id) is not None


def _nudge_time_local(db: Session, user_id: int) -> tuple[time, ZoneInfo]:
    """The daily send time: her daily-nudge time if set, else a gentle
    mid-morning default — in her timezone."""
    settings = settings_service.get_settings(db, user_id)
    raw = settings["daily_nudge_time"].strip() or "09:00"
    hour, minute = (int(part) for part in raw.split(":"))
    try:
        tz = ZoneInfo(settings["timezone"])
    except Exception:
        tz = ZoneInfo("UTC")
    return time(hour, minute), tz


def _first_occurrence(
    event_date: date, days_before: int, send_time: time, tz: ZoneInfo
) -> datetime | None:
    """The first UTC moment to nudge: `days_before` days out (or the next
    send-time still ahead of us, if that window already started), never
    past the event day. None if the event is entirely behind us."""
    now_local = datetime.now(tz)
    start_day = max(event_date - timedelta(days=days_before), now_local.date())
    candidate = datetime.combine(start_day, send_time, tzinfo=tz)
    if candidate <= now_local:
        candidate += timedelta(days=1)
    if candidate.date() > event_date:
        return None
    return candidate.astimezone(timezone.utc)


def sync_countdown_reminder(
    db: Session,
    user: User,
    packing_list: PackingList,
    enabled: bool,
    days_before: int = DEFAULT_REMINDER_DAYS_BEFORE,
) -> None:
    """Create or clear the list's countdown reminder to match her choice.

    One active reminder per list at most. The body stored here is a
    placeholder — the cron composes the real one at send time from the
    live unpacked count, so it's never stale. Caller commits."""
    existing = _get_countdown(db, packing_list.id)

    wants = (
        enabled
        and packing_list.event_date is not None
        and packing_list.status == "active"
        and not packing_list.is_template
    )
    if not wants:
        if existing is not None:
            existing.active = False
        return

    send_time, tz = _nudge_time_local(db, user.id)
    scheduled_for = _first_occurrence(
        packing_list.event_date, days_before, send_time, tz
    )
    if scheduled_for is None:
        if existing is not None:
            existing.active = False
        return

    if existing is None:
        db.add(
            Reminder(
                user_id=user.id,
                packing_list_id=packing_list.id,
                title=packing_list.name,
                body="",  # composed live at send time
                scheduled_for=scheduled_for,
                recurrence_rule=COUNTDOWN_RULE,
                active=True,
            )
        )
    else:
        existing.scheduled_for = scheduled_for
        existing.last_sent_at = None


def advance_countdown_reminder(
    db: Session, reminder: Reminder, packing_list: PackingList, user: User
) -> None:
    """After the cron sends a countdown nudge, roll it to the same local
    time tomorrow — or retire it once the event day has been nudged.
    Caller commits."""
    send_time, tz = _nudge_time_local(db, user.id)
    next_local = datetime.now(tz).date() + timedelta(days=1)
    if packing_list.event_date is None or next_local > packing_list.event_date:
        reminder.active = False
        return
    reminder.scheduled_for = datetime.combine(
        next_local, send_time, tzinfo=tz
    ).astimezone(timezone.utc)


def compose_countdown(
    packing_list: PackingList, today: date, first_name: str
) -> tuple[str, str] | None:
    """The countdown push, composed at send time so the unpacked count is
    live. Returns None when there's nothing kind to say (event passed).
    Voice: warm, no-guilt — a heads-up with a finish line, never a nag."""
    if packing_list.event_date is None or today > packing_list.event_date:
        return None

    days_left = (packing_list.event_date - today).days
    if days_left == 0:
        when = "is today"
    elif days_left == 1:
        when = "is tomorrow"
    else:
        when = f"is in {days_left} days"

    packed, total = progress(packing_list)
    remaining = total - packed

    title = f"{packing_list.name} {when} 🧳"
    if remaining == 0:
        body = f"You're all packed, {first_name} — everything's ready. Enjoy! 🎉"
    elif remaining == 1:
        body = "Just 1 item left to pack — you're basically done ✨"
    else:
        body = (
            f"{remaining} items still to pack — plenty of time. "
            "Tap in whenever you're ready."
        )
    return title, body
