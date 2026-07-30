"""The decay engine (SPEC §4) — the heart of Tada.

Every prioritization feature in the app (daily focus, "I have X minutes",
room sessions, room aggregate colors, the daily nudge) reads the one
signal computed here: the dirtiness ratio.

    ratio = (now - last_done_at) / cadence_days

A task with no fixed due date just gets "dirtier" as the ratio climbs;
completing it resets last_done_at and the curve restarts. Tune the
constants below — they are deliberately collected at the top because this
module will be read and adjusted often.
"""

from datetime import datetime, timedelta, timezone, tzinfo

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.completion_log import CompletionLog
from app.models.room import Room
from app.models.task import Task
from app.models.user import User

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

#: A never-done task is treated as this ratio — high priority (>= 1.2 is
#: "overdue"), but not so high it drowns out genuinely ancient tasks.
NEVER_DONE_RATIO = 1.5

#: Added to the priority score of daily-cadence tasks that haven't been
#: done today (ratio >= 1.0), so dailies reliably surface each day even
#: against longer-cadence tasks with slightly higher ratios (SPEC §4).
DAILY_BOOST = 0.5

#: Added on a task's preferred day (and the following grace day) — Phase
#: 8. A BOOST, never a schedule: strong enough that weekly laundry at
#: ratio ~1.0 scores ~3.0 on Saturday and leads over anything overdue or
#: never-done (1.5) in normal conditions, while a truly neglected task —
#: three-plus cadences past due — can still edge above it. Additive, not
#: a pin, so tasks sharing a preferred day keep their decay order.
PREFERRED_DAY_BOOST = 2.0

#: Color band thresholds (SPEC §4).
BAND_AGING = 0.5   # below: fresh (green)
BAND_DUE = 0.9     # below: aging (yellow)
BAND_OVERDUE = 1.2  # below: due (orange); at/above: overdue (red)

#: Cap on how many tasks a single focus session will queue up — a session
#: is a guided sprint, never a wall of work.
MAX_SESSION_TASKS = 10

#: Snooze options (SPEC §6): defer the *reminder*, never the decay.
#: Deliberately simple fixed offsets.
SNOOZE_OFFSETS: dict[str, timedelta] = {
    "later_today": timedelta(hours=3),
    "tomorrow": timedelta(hours=24),
    "few_days": timedelta(days=3),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    """Postgres (timestamptz) returns tz-aware datetimes; SQLite (local
    dev/tests) returns naive UTC. Normalize so the math never crashes."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# The core signal
# ---------------------------------------------------------------------------

def dirtiness_ratio(task: Task, now: datetime | None = None) -> float:
    """How "dirty" a task is: elapsed time since last done, as a fraction
    of its cadence. 0.0 = just done, 1.0 = exactly one cadence elapsed.
    Never-done tasks read as NEVER_DONE_RATIO (high priority)."""
    if task.last_done_at is None:
        return NEVER_DONE_RATIO
    now = now or _utcnow()
    elapsed = (now - _aware(task.last_done_at)).total_seconds()
    cadence_seconds = task.cadence_days * 86400
    return max(0.0, elapsed / cadence_seconds)


def band_for_ratio(ratio: float) -> str:
    """Map a ratio onto the SPEC §4 color bands."""
    if ratio < BAND_AGING:
        return "fresh"
    if ratio < BAND_DUE:
        return "aging"
    if ratio < BAND_OVERDUE:
        return "due"
    return "overdue"


def preferred_day_boost(
    task: Task, now: datetime | None = None, tz: tzinfo | None = None
) -> float:
    """The Phase 8 preferred-day boost — a preference, never a deadline.

    Boosted on the preferred day and the following day (the grace day:
    laundry set to Saturday is boosted Saturday, boosted Sunday if it
    didn't happen, then quiet until next Saturday). "Today" is her local
    day, so `tz` should come from her settings; without it, UTC.

    Fresh tasks never boost: done on Wednesday, laundry decays normally
    and Saturday simply stays quiet — that is the whole answer to "does
    Saturday still fire?", and it keeps the planning list honest too.
    Ranking only — dirtiness, bands, and last_done_at are untouched, and
    missing the day carries no penalty and no overdue state anywhere."""
    if task.preferred_day is None:
        return 0.0
    if dirtiness_ratio(task, now) < BAND_AGING:
        return 0.0
    now = now or _utcnow()
    today = now.astimezone(tz or timezone.utc).weekday()  # Monday = 0
    grace_day = (task.preferred_day + 1) % 7
    if today in (task.preferred_day, grace_day):
        return PREFERRED_DAY_BOOST
    return 0.0


def priority_score(
    task: Task, now: datetime | None = None, tz: tzinfo | None = None
) -> float:
    """The ranking signal: the ratio, plus the boost that keeps daily
    tasks surfacing every day (SPEC §4), plus the Phase 8 preferred-day
    boost."""
    ratio = dirtiness_ratio(task, now)
    if task.cadence_days == 1 and ratio >= 1.0:
        ratio += DAILY_BOOST
    return ratio + preferred_day_boost(task, now, tz)


def is_snoozed(task: Task, now: datetime | None = None) -> bool:
    now = now or _utcnow()
    return task.snoozed_until is not None and _aware(task.snoozed_until) > now


def rank_tasks(
    tasks: list[Task], now: datetime | None = None, tz: tzinfo | None = None
) -> list[Task]:
    """Priority ranking (SPEC §4): score (= ratio + boosts) descending.
    Tie-breaks: higher raw ratio (which also puts overdue before due),
    then longer since last_done_at, with never-done counting as longest.
    `tz` (her local timezone) anchors the preferred-day boost's "today"."""
    now = now or _utcnow()
    beginning = datetime.min.replace(tzinfo=timezone.utc)

    def sort_key(task: Task):
        return (
            -priority_score(task, now, tz),
            -dirtiness_ratio(task, now),
            _aware(task.last_done_at) if task.last_done_at else beginning,
        )

    return sorted(tasks, key=sort_key)


# ---------------------------------------------------------------------------
# Candidate selection & the daily-use lenses (SPEC §6)
# ---------------------------------------------------------------------------

def candidate_tasks(
    db: Session,
    *,
    for_user_id: int | None = None,
    room_id: int | None = None,
    effort: str | None = None,
    zone_id: int | None = None,
    guest_only: bool = False,
    now: datetime | None = None,
    tz: tzinfo | None = None,
) -> list[Task]:
    """Active, un-snoozed tasks matching the lens filters, priority-ranked.

    Fresh tasks (ratio < 0.5) are excluded: the app guides toward what
    actually needs doing, and when nothing does it celebrates instead of
    inventing work — that calm is part of the no-guilt design.

    With `for_user_id` set (Phase 2), tasks assigned to a *different*
    member are excluded — delegated work shouldn't nag the owner. Her own
    and unassigned tasks (claimable or not) still surface.

    The Phase 3 overlays are just two more filters over the same ranking:
    `zone_id` scopes to the rooms mapped into a FlyLady zone, and
    `guest_only` is Chaos Cleaning — guest-facing tasks only, deep work
    skipped, because with company coming the win is fast visible impact
    (SPEC §6)."""
    now = now or _utcnow()
    query = (
        select(Task)
        .options(joinedload(Task.room))
        .where(Task.is_active.is_(True), Task.category == "cleaning")
    )
    if for_user_id is not None:
        query = query.where(
            (Task.assignee_id.is_(None)) | (Task.assignee_id == for_user_id)
        )
    if room_id is not None:
        query = query.where(Task.room_id == room_id)
    if zone_id is not None:
        query = query.join(Task.room).where(Room.zone_id == zone_id)
    if guest_only:
        query = query.where(Task.guest_facing.is_(True), Task.effort == "quick")
    if effort in ("quick", "deep"):
        query = query.where(Task.effort == effort)

    tasks = list(db.scalars(query).all())
    eligible = [
        t
        for t in tasks
        if not is_snoozed(t, now) and dirtiness_ratio(t, now) >= BAND_AGING
    ]
    return rank_tasks(eligible, now, tz)


def daily_focus(
    db: Session,
    *,
    limit: int,
    for_user_id: int | None = None,
    effort: str | None = None,
    now: datetime | None = None,
    tz: tzinfo | None = None,
) -> list[Task]:
    """The calm home screen (SPEC §6): the top `limit` tasks by priority —
    never a wall. An empty result means the home is genuinely in good
    shape and the UI should say so warmly."""
    return candidate_tasks(
        db, for_user_id=for_user_id, effort=effort, now=now, tz=tz
    )[:limit]


def build_session(
    db: Session,
    *,
    minutes: int | None = None,
    for_user_id: int | None = None,
    room_id: int | None = None,
    effort: str | None = None,
    zone_id: int | None = None,
    guest_only: bool = False,
    exclude_ids: set[int] | None = None,
    now: datetime | None = None,
    tz: tzinfo | None = None,
) -> list[Task]:
    """Build the ordered task list for a focus session (SPEC §5).

    With a time budget: greedily walk the priority ranking and take each
    task whose estimate still fits the remaining minutes — highest-priority
    work first, sized to the time she actually has. Without a budget
    (picking a room): the room's non-fresh tasks in priority order.
    Always capped at MAX_SESSION_TASKS — it's a coached sprint, not a dump.

    The Phase 3 lenses ride the same flow: `guest_only` builds the
    "company in [time]" punch list, `zone_id` builds "this week's zone".
    `exclude_ids` (Phase 5) keeps a timer-extend top-up from re-offering
    tasks already in her running session queue.
    """
    candidates = candidate_tasks(
        db,
        for_user_id=for_user_id,
        room_id=room_id,
        effort=effort,
        zone_id=zone_id,
        guest_only=guest_only,
        now=now,
        tz=tz,
    )
    if exclude_ids:
        candidates = [t for t in candidates if t.id not in exclude_ids]

    if minutes is None:
        return candidates[:MAX_SESSION_TASKS]

    picked: list[Task] = []
    remaining = minutes
    for task in candidates:
        if len(picked) >= MAX_SESSION_TASKS:
            break
        if task.estimated_minutes <= remaining:
            picked.append(task)
            remaining -= task.estimated_minutes
    return picked


def chores_for_user(
    db: Session, user_id: int, now: datetime | None = None, tz: tzinfo | None = None
) -> tuple[list[Task], list[Task]]:
    """The kid surface (SPEC §6 multi-user): (my chores, up for grabs),
    each priority-ranked.

    "My chores" = active tasks assigned to this member; "up for grabs" =
    active unassigned tasks the owner marked claimable. The same non-fresh
    gate as every doing-surface applies, so a chore disappears once done
    and quietly returns when it needs doing again — same decay engine, no
    separate chore system. Assignment is explicit, so category isn't
    filtered here (an assigned maintenance job is still a chore)."""
    now = now or _utcnow()
    tasks = db.scalars(
        select(Task).options(joinedload(Task.room)).where(Task.is_active.is_(True))
    ).all()
    eligible = [
        t
        for t in tasks
        if not is_snoozed(t, now) and dirtiness_ratio(t, now) >= BAND_AGING
    ]
    mine = rank_tasks([t for t in eligible if t.assignee_id == user_id], now, tz)
    up_for_grabs = rank_tasks(
        [t for t in eligible if t.assignee_id is None and t.claimable], now, tz
    )
    return mine, up_for_grabs


def room_aggregate_ratio(tasks: list[Task], now: datetime | None = None) -> float | None:
    """Room-level dirtiness (SPEC §4): a blend of the room's worst task and
    its average — "roughly the max/average" — so one overdue task colors
    the room without a single red drowning nine greens. None if the room
    has no active tasks."""
    now = now or _utcnow()
    ratios = [dirtiness_ratio(t, now) for t in tasks if t.is_active]
    if not ratios:
        return None
    return 0.5 * max(ratios) + 0.5 * (sum(ratios) / len(ratios))


# ---------------------------------------------------------------------------
# State changes
# ---------------------------------------------------------------------------

def complete_task(
    db: Session,
    task: Task,
    user: User,
    source: str,
    now: datetime | None = None,
) -> CompletionLog:
    """Completion (SPEC §4): reset the decay curve, clear any snooze, and
    write the permanent CompletionLog row. Phase 5 rides the same seam:
    the streak advances and badges are checked here, so every completion
    path — home screen, sessions, kid chores, overlays — counts exactly
    once. Caller commits."""
    # Local import: the reward layer reads settings and history; keeping
    # it out of the module scope keeps the decay engine itself pure.
    from app.services import badges as badge_service
    from app.services import streaks

    now = now or _utcnow()
    # Captured before the overwrite (Phase 9): the exact value undo
    # restores. NULL on a first-ever completion is legitimate — undo of
    # that returns the task to never-done.
    previous_last_done_at = task.last_done_at
    task.last_done_at = now
    task.snoozed_until = None
    log = CompletionLog(
        task_id=task.id,
        completed_by=user.id,
        completed_at=now,
        source=source,
        previous_last_done_at=previous_last_done_at,
    )
    db.add(log)
    db.flush()  # the badge checks below count this completion too

    streaks.update_streak(db, user, now)
    badge_service.evaluate_completion(db, user, now)
    return log


class UndoWindowClosed(Exception):
    """An undo was asked of a completion from a previous day. Older
    corrections go through the Phase 4.6 last-done editor instead."""


def undo_completion(
    db: Session,
    log: CompletionLog,
    now: datetime | None = None,
    tz: tzinfo | None = None,
) -> Task:
    """Undo a completion (Phase 9): reverse the DECAY STATE ONLY.

    Restores task.last_done_at from the value the completion overwrote
    (NULL preserved as NULL — a first-ever completion undoes back to
    never-done) and deletes the log row. Deliberately untouched:
    - streaks (current_streak, longest_streak, last_active_date) — one
      mis-tap plus a correction must never cost a 30-day streak; streaks
      only ever go up.
    - badges — earned once, never revoked (SPEC §5).
    - snoozed_until — completion cleared it and undo does not bring a
      snooze back; she can snooze again in a tap.

    Only today's completions qualify ("today" in her local day via `tz`);
    anything older raises UndoWindowClosed — the Phase 4.6 editable
    last-done date already covers history. Caller commits."""
    now = now or _utcnow()
    local = tz or timezone.utc
    if _aware(log.completed_at).astimezone(local).date() != now.astimezone(local).date():
        raise UndoWindowClosed(
            "That one's from a previous day — you can adjust the task's "
            "last-done date instead."
        )
    task = db.get(Task, log.task_id)
    task.last_done_at = log.previous_last_done_at
    db.delete(log)
    db.flush()
    return task


def snooze_task(task: Task, option: str, now: datetime | None = None) -> datetime:
    """Decay-aware snooze (SPEC §6): hide the task from focus surfaces
    until the chosen time WITHOUT touching last_done_at — it keeps aging
    quietly and simply resurfaces. `option` "wake" clears an active snooze
    early. Returns the new snoozed_until (or now, for wake)."""
    now = now or _utcnow()
    if option == "wake":
        task.snoozed_until = None
        return now
    task.snoozed_until = now + SNOOZE_OFFSETS[option]
    return task.snoozed_until
