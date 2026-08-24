"""Lists (Phase 6, grown out of Phase 4's packing module) — a
self-contained module, deliberately apart from the cleaning core.

Lists are one-off: no decay, no cadence, no last_done_at, and nothing
here touches services/scheduling.py or the focus-session flow. List
items must NEVER surface on the daily focus home screen or in a focus
session — cleaning tasks recur and decay; list items are done once and
gone. It's also the one place a full grouped checklist beats
one-at-a-time — you want the whole list visible so nothing is forgotten.

What it reuses so it feels native: the design system (frontend) and the
existing Reminder + Web Push plumbing, via an optional countdown nudge
tied to a list's event date ("Trip in 3 days — 6 items still to pack").
"""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.lists import List, ListItem, ListSection
from app.models.reminder import Reminder
from app.models.user import User
from app.services import settings_service
from app.services.list_templates import TEMPLATES

#: recurrence_rule marker for countdown reminders — the cron recognizes
#: them by list_id, this just keeps rows readable. (Rows created before
#: Phase 6 carry the old "packing_countdown" marker; both are inert.)
#: Since issue #19 the chosen lead rides along as "list_countdown:<n>"
#: — the session-timer pattern — so a later re-sync can't forget it.
COUNTDOWN_RULE = "list_countdown"

#: Default lead time for the countdown nudge when none is given.
DEFAULT_REMINDER_DAYS_BEFORE = 3


# ---------------------------------------------------------------------------
# Templates & cloning
# ---------------------------------------------------------------------------

def seed_templates(db: Session) -> None:
    """Create any starter templates whose *kind* has none yet. Seeding
    per kind keeps this idempotent — once a kind's templates exist they
    are never re-added or overwritten (her edits are safe) — while still
    letting a later phase ship a new kind's templates into an existing
    database (Phase 6 adds the "shopping" group this way). Caller
    commits."""
    seeded_kinds = set(
        db.scalars(select(List.kind).where(List.is_template.is_(True)).distinct()).all()
    )

    for kind, name, sections in TEMPLATES:
        if kind in seeded_kinds:
            continue
        template = List(name=name, kind=kind, is_template=True)
        template.sections = [
            ListSection(
                name=section_name,
                sort_order=section_index,
                items=[
                    ListItem(name=item_name, sort_order=item_index)
                    for item_index, item_name in enumerate(item_names)
                ],
            )
            for section_index, (section_name, item_names) in enumerate(sections)
        ]
        db.add(template)
    db.flush()


def clone_list(
    db: Session,
    source: List,
    name: str,
    event_date: date | None,
    destination: str | None = None,
    duration: str | None = None,
) -> List:
    """Clone any list — a template or an archived one, the same move —
    into a fresh active list: same sections and items, every checkbox
    cleared. Prices ride along (reusing a shopping list means buying the
    same things). Destination/duration belong to the new trip, so they
    come from the caller (never copied from the source). Caller commits."""
    new_list = List(
        name=name,
        kind=source.kind,
        is_template=False,
        event_date=event_date,
        destination=destination,
        duration=duration,
        status="active",
    )
    new_list.sections = [
        ListSection(
            name=section.name,
            sort_order=section.sort_order,
            items=[
                ListItem(
                    name=item.name,
                    quantity=item.quantity,
                    notes=item.notes,
                    packed=False,
                    price=item.price,
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
# Progress & totals
# ---------------------------------------------------------------------------

def progress(parent_list: List) -> tuple[int, int]:
    """(checked, total) across every section of the list."""
    items = [item for section in parent_list.sections for item in section.items]
    return sum(1 for item in items if item.packed), len(items)


def section_progress(section: ListSection) -> tuple[int, int]:
    """(checked, total) for one section."""
    return sum(1 for item in section.items if item.packed), len(section.items)


def price_totals(parent_list: List) -> tuple[Decimal, Decimal] | None:
    """(checked total, list total) across the list's priced items, or
    None when no item carries a price — so a packing list never sprouts
    a pointless $0.00. On a shopping list "checked" means bought, so the
    checked total reads as spend-to-date. Computed, never stored."""
    priced = [
        item
        for section in parent_list.sections
        for item in section.items
        if item.price is not None
    ]
    if not priced:
        return None
    total = sum((item.price for item in priced), Decimal("0"))
    checked = sum((item.price for item in priced if item.packed), Decimal("0"))
    return checked, total


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


def move_section(db: Session, section: ListSection, new_index: int) -> None:
    """Reposition a section within its list. Caller commits."""
    siblings = list(
        db.scalars(
            select(ListSection)
            .where(ListSection.list_id == section.list_id)
            .order_by(ListSection.sort_order, ListSection.id)
        ).all()
    )
    _reindex(siblings, section, new_index)


def move_item(db: Session, item: ListItem, new_index: int) -> None:
    """Reposition an item within its section. Caller commits."""
    siblings = list(
        db.scalars(
            select(ListItem)
            .where(ListItem.section_id == item.section_id)
            .order_by(ListItem.sort_order, ListItem.id)
        ).all()
    )
    _reindex(siblings, item, new_index)


# ---------------------------------------------------------------------------
# The countdown reminder (reuses the Phase 0/1 Reminder + push plumbing)
# ---------------------------------------------------------------------------

def _get_countdown(db: Session, list_id: int) -> Reminder | None:
    return db.scalar(
        select(Reminder).where(
            Reminder.list_id == list_id, Reminder.active.is_(True)
        )
    )


def reminder_enabled(db: Session, parent_list: List) -> bool:
    """Whether a live countdown reminder exists for this list."""
    return _get_countdown(db, parent_list.id) is not None


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


def _persisted_days_before(reminder: Reminder | None) -> int | None:
    """The lead persisted in a countdown reminder's rule
    ("list_countdown:<n>"), or None for pre-#19 rows without a suffix."""
    if reminder is None or not reminder.recurrence_rule:
        return None
    _, _, days = reminder.recurrence_rule.partition(":")
    return int(days) if days.isdigit() else None


def sync_countdown_reminder(
    db: Session,
    user: User,
    parent_list: List,
    enabled: bool,
    days_before: int | None = None,
) -> None:
    """Create or clear the list's countdown reminder to match her choice.

    One active reminder per list at most. The body stored here is a
    placeholder — the cron composes the real one at send time from the
    live unchecked count, so it's never stale. `days_before=None` means
    "not chosen this time": the lead persisted on the list's most recent
    reminder row wins — including a deactivated one, so toggling the
    nudge off and back on keeps it too (issue #19 — nothing but an
    explicit choice may move her 14-day nudge to the default 3). A
    re-enable revives that row rather than adding another. Caller
    commits."""
    existing = _get_countdown(db, parent_list.id) or db.scalar(
        select(Reminder)
        .where(Reminder.list_id == parent_list.id)
        .order_by(Reminder.id.desc())
        .limit(1)
    )
    if days_before is None:
        days_before = _persisted_days_before(existing)
    if days_before is None:
        days_before = DEFAULT_REMINDER_DAYS_BEFORE

    wants = (
        enabled
        and parent_list.event_date is not None
        and parent_list.status == "active"
        and not parent_list.is_template
    )
    if not wants:
        if existing is not None:
            existing.active = False
        return

    send_time, tz = _nudge_time_local(db, user.id)
    scheduled_for = _first_occurrence(
        parent_list.event_date, days_before, send_time, tz
    )
    if scheduled_for is None:
        if existing is not None:
            existing.active = False
        return

    if existing is None:
        db.add(
            Reminder(
                user_id=user.id,
                list_id=parent_list.id,
                title=parent_list.name,
                body="",  # composed live at send time
                scheduled_for=scheduled_for,
                recurrence_rule=f"{COUNTDOWN_RULE}:{days_before}",
                active=True,
            )
        )
    else:
        existing.scheduled_for = scheduled_for
        existing.last_sent_at = None
        existing.recurrence_rule = f"{COUNTDOWN_RULE}:{days_before}"
        existing.active = True


def advance_countdown_reminder(
    db: Session, reminder: Reminder, parent_list: List, user: User
) -> None:
    """After the cron sends a countdown nudge, roll it to the same local
    time tomorrow — or retire it once the event day has been nudged.
    Caller commits."""
    send_time, tz = _nudge_time_local(db, user.id)
    next_local = datetime.now(tz).date() + timedelta(days=1)
    if parent_list.event_date is None or next_local > parent_list.event_date:
        reminder.active = False
        return
    reminder.scheduled_for = datetime.combine(
        next_local, send_time, tzinfo=tz
    ).astimezone(timezone.utc)


def compose_countdown(
    parent_list: List, today: date, first_name: str
) -> tuple[str, str] | None:
    """The countdown push, composed at send time so the unchecked count
    is live. Returns None when there's nothing kind to say (event
    passed). Voice: warm, no-guilt — a heads-up with a finish line,
    never a nag."""
    if parent_list.event_date is None or today > parent_list.event_date:
        return None

    days_left = (parent_list.event_date - today).days
    if days_left == 0:
        when = "is today"
    elif days_left == 1:
        when = "is tomorrow"
    else:
        when = f"is in {days_left} days"

    checked, total = progress(parent_list)
    remaining = total - checked

    # Kind flavors the emoji and the verb; the shape stays the same.
    emoji = {"packing": "🧳", "shopping": "🛒"}.get(parent_list.kind, "📋")
    verb = "pack" if parent_list.kind == "packing" else "check off"

    title = f"{parent_list.name} {when} {emoji}"
    if remaining == 0:
        body = f"You're all set, {first_name} — everything's checked off. Enjoy! 🎉"
    elif remaining == 1:
        body = f"Just 1 item left to {verb} — you're basically done ✨"
    else:
        body = (
            f"{remaining} items still to {verb} — plenty of time. "
            "Tap in whenever you're ready."
        )
    return title, body
