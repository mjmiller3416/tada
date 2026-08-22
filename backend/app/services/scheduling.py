"""The decay engine (SPEC §4) — the heart of Tada.

Every prioritization feature in the app (daily focus, "I have X minutes",
room sessions, room aggregate colors, the daily nudge) reads the one
signal computed here: the dirtiness ratio.

    ratio = (now - last_done_at) / cadence_days

A task with no fixed due date just gets "dirtier" as the ratio climbs;
completing it resets last_done_at and the curve restarts. Tune the
constants below — they are deliberately collected at the top because this
module will be read and adjusted often.

Phase 10 (SPEC §4 scheduling lanes): decay is the scheduler for
*recurring* work, no longer the only one. `task_type` says which clock
governs a task, and each lane gets its own selector —
recurring_candidates / zone_candidates / project_candidates — instead of
more switches inside one candidate query.

Phase 11 composes those selectors into the surfaces: compose_focus (the
home screen's 1–3 cards), compose_session (timed and room sessions with
at most one current-zone mission), and zone_mission_session (mission-only
zone sessions). All of it gates on settings_service.lanes_active — with
the flag or the zones overlay off, candidate_tasks() still serves every
surface exactly as it always has. That is the permanent rollback
boundary.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.completion_log import CompletionLog
from app.models.room import Room
from app.models.task import Task
from app.models.user import User
from app.models.zone import Zone

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

#: The task types whose clock is decay (SPEC §4 lanes, Phase 10). Zone
#: missions and projects are the two types scheduled by something else —
#: the zone calendar and her explicit choice, respectively.
RECURRING_TYPES = ("routine", "weekly_blessing", "maintenance")

#: The "weekly" cadence tier (SPEC §6). The ONE place the app steps off
#: "decay, not a calendar" (SPEC §1): a weekly-cadence chore on the kid
#: chore surface resets on a fixed Monday rather than rolling decay — see
#: chores_for_user. Everywhere else, cadence 7 is just a decay rate.
WEEKLY_CADENCE_DAYS = 7


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
    (SPEC §6).

    Maintenance stays in its own section (SPEC §6): the filter reads
    task_type (Phase 10 — category is deprecated). Projects are excluded
    too (issue #20): "project = manual only, NEVER automatic" holds on
    every path, so a task reclassified to project during the Phase 11
    review — while the lane flag is still off — never floods daily focus
    at never-done priority. Every other type keeps the old
    single-universe behavior until Phase 11's composer takes over.

    Snoozed ("resting") tasks surface too once nothing un-snoozed is left
    (see `_doing_eligible`) — still flagged `is_snoozed`, so the surface
    shows what's left without waking anything early."""
    now = now or _utcnow()
    query = (
        select(Task)
        .options(joinedload(Task.room))
        .where(
            Task.is_active.is_(True),
            Task.task_type.notin_(("maintenance", "project")),
        )
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
        # Routines ONLY (Phase 11, SPEC §6) — not merely "no zone or
        # project" (issue #22): "wipe cabinet fronts" may be flagged
        # guest-facing, but a zone mission, a project, and a whole-home
        # weekly blessing are all the wrong shape for a
        # company-in-twenty-minutes punch list.
        query = query.where(
            Task.guest_facing.is_(True),
            Task.effort == "quick",
            Task.task_type == "routine",
        )
    if effort in ("quick", "deep"):
        query = query.where(Task.effort == effort)

    tasks = list(db.scalars(query).all())
    return rank_tasks(_doing_eligible(tasks, now), now, tz)


# ---------------------------------------------------------------------------
# Scheduling lanes (SPEC §4, Phase 10) — one experience, multiple clocks
#
# Decay schedules recurring upkeep; the zone calendar schedules detailed
# and decluttering missions; manual projects never create debt. The lanes
# share one calm interface and one completion path — they do NOT share one
# eligibility rule, which is why each gets its own selector rather than
# more switches inside candidate_tasks(). Built and tested in Phase 10;
# wired to surfaces by Phase 11's composer behind zone_lane_enabled.
# ---------------------------------------------------------------------------

def _doing_eligible(tasks: list[Task], now: datetime) -> list[Task]:
    """The doing-surface gate every automatic lane shares: non-fresh
    (ratio >= BAND_AGING) tasks that aren't resting (snoozed) — the app
    guides toward what actually needs doing, and celebrates when nothing
    does.

    Resting tasks stay excluded while any other non-fresh task remains;
    once those are all caught up, resting tasks surface too so she can
    see what's left, still flagged `is_snoozed` — surfacing them is a
    visibility change only, never an early wake (SPEC §6 decay-aware
    snooze: it defers the reminder, not the task)."""
    non_resting = [
        t
        for t in tasks
        if not is_snoozed(t, now) and dirtiness_ratio(t, now) >= BAND_AGING
    ]
    if non_resting:
        return non_resting
    return [
        t
        for t in tasks
        if is_snoozed(t, now) and dirtiness_ratio(t, now) >= BAND_AGING
    ]


def recurring_candidates(
    db: Session,
    *,
    for_user_id: int | None = None,
    room_id: int | None = None,
    zone_id: int | None = None,
    effort: str | None = None,
    now: datetime | None = None,
    tz: tzinfo | None = None,
) -> list[Task]:
    """The decay lane: tasks whose clock is decay — routine,
    weekly_blessing, and maintenance — priority-ranked. A rename-and-
    narrow of candidate_tasks(): the same assignment exclusion, snooze
    and freshness gates, and room/effort filters; zone missions and
    projects run on different clocks and are never admitted here.
    `zone_id` scopes to the rooms mapped into a zone — the "recurring
    work from that zone's rooms" half of Phase 11's repurposed
    home-screen zone selector."""
    now = now or _utcnow()
    query = (
        select(Task)
        .options(joinedload(Task.room))
        .where(Task.is_active.is_(True), Task.task_type.in_(RECURRING_TYPES))
    )
    if for_user_id is not None:
        query = query.where(
            (Task.assignee_id.is_(None)) | (Task.assignee_id == for_user_id)
        )
    if room_id is not None:
        query = query.where(Task.room_id == room_id)
    if zone_id is not None:
        query = query.join(Task.room).where(Room.zone_id == zone_id)
    if effort in ("quick", "deep"):
        query = query.where(Task.effort == effort)
    return rank_tasks(_doing_eligible(list(db.scalars(query).all()), now), now, tz)


def zone_candidates(
    db: Session,
    *,
    for_user_id: int,
    zone_id: int | None = None,
    effort: str | None = None,
    now: datetime | None = None,
    tz: tzinfo | None = None,
) -> list[Task]:
    """The zone lane: task_type='zone' missions whose room maps into the
    zone, ranked by the same decay priority WITHIN the pool.

    With zone_id=None — the automatic "what should I do" path — the
    BACKEND derives the current zone from today's date in her local
    timezone (the client is never trusted to say which zone is "now"),
    and returns nothing when the zones overlay is off or no zone matches
    this week. Passing an explicit zone_id is the planning/manual path:
    it retrieves that zone's missions even out of window, and skips the
    overlay gate — asking for a specific zone IS the opt-in.

    The no-debt rule (SPEC §4) rides on this being pure selection: out of
    window a mission is simply not admitted — nothing is rescheduled,
    logged, or mutated — and when its zone comes round again it is
    eligible with history intact. Its internal ratio may pass 1.2
    meanwhile; presenting that quietly (never as red debt) is Phase 11's
    waiting state."""
    # Local imports, same pattern as complete_task(): the zone calendar
    # and settings live outside the engine, and the engine stays pure.
    from app.services import settings_service
    from app.services import zones as zone_service

    now = now or _utcnow()
    if zone_id is None:
        if settings_service.get_setting(db, for_user_id, "zones_enabled") != "true":
            return []
        local_tz = tz or settings_service.user_timezone(db, for_user_id)
        zone = zone_service.zone_for_moment(db, now, local_tz)
        if zone is None:
            return []
        zone_id = zone.id
    else:
        zone = db.get(Zone, zone_id)

    # Zone 3's rotating second room (Phase 11, SPEC §6): while the
    # setting names a room, that room's zone missions join Zone 3's pool.
    # A one-line union, not a membership table.
    room_filter = Room.zone_id == zone_id
    if zone is not None and zone.week_of_month == 3:
        extra_room_id = settings_service.zone_3_extra_room_id(db, for_user_id)
        if extra_room_id is not None:
            room_filter = or_(Room.zone_id == zone_id, Room.id == extra_room_id)

    query = (
        select(Task)
        .options(joinedload(Task.room))
        .join(Task.room)
        .where(
            Task.is_active.is_(True),
            Task.task_type == "zone",
            room_filter,
            (Task.assignee_id.is_(None)) | (Task.assignee_id == for_user_id),
        )
    )
    if effort in ("quick", "deep"):
        query = query.where(Task.effort == effort)
    return rank_tasks(_doing_eligible(list(db.scalars(query).all()), now), now, tz)


def project_candidates(
    db: Session,
    *,
    for_user_id: int | None = None,
    now: datetime | None = None,
    tz: tzinfo | None = None,
) -> list[Task]:
    """The manual lane: task_type='project', priority-ranked. Calling
    this IS the explicit request — projects never enter automatic
    selection (both other selectors exclude the type) and never create
    debt. No freshness gate either: she asked to see her projects, and a
    project doesn't "need doing" on any clock but hers."""
    now = now or _utcnow()
    query = (
        select(Task)
        .options(joinedload(Task.room))
        .where(Task.is_active.is_(True), Task.task_type == "project")
    )
    if for_user_id is not None:
        query = query.where(
            (Task.assignee_id.is_(None)) | (Task.assignee_id == for_user_id)
        )
    return rank_tasks(list(db.scalars(query).all()), now, tz)


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


def _greedy_fill(candidates: list[Task], minutes: int) -> list[Task]:
    """The SPEC §5 time-budget fill: walk the priority ranking and take
    each task whose estimate still fits the remaining minutes — highest-
    priority work first, sized to the time she actually has, capped at
    MAX_SESSION_TASKS."""
    picked: list[Task] = []
    remaining = minutes
    for task in candidates:
        if len(picked) >= MAX_SESSION_TASKS:
            break
        if task.estimated_minutes <= remaining:
            picked.append(task)
            remaining -= task.estimated_minutes
    return picked


# ---------------------------------------------------------------------------
# The Phase 11 composer — one calm interface over multiple clocks
#
# Every function here is called ONLY when settings_service.lanes_active
# says so (the zone_lane_enabled flag AND the zones overlay both on).
# Otherwise the routers stay on candidate_tasks()/daily_focus()/
# build_session() and the app is exactly its pre-lane self.
# ---------------------------------------------------------------------------

def compose_focus(
    db: Session,
    *,
    limit: int,
    for_user_id: int,
    effort: str | None = None,
    now: datetime | None = None,
    tz: tzinfo | None = None,
) -> list[Task]:
    """The composed home screen (SPEC §6): the same calm 1–3 cards, newly
    sourced across lanes. Card 1 is the top recurring candidate, card 2
    the single best mission from the CURRENT zone (backend-derived — the
    client never says which zone is "now"), card 3 the next recurring
    candidate. No eligible mission just means another recurring card —
    never an empty slot — and `limit` (daily_focus_count) still caps the
    total. The energy filter applies to BOTH pools: a five-minute task
    can still mean painful scrubbing, and low-energy days deserve
    low-energy missions too."""
    now = now or _utcnow()
    cards = list(
        recurring_candidates(db, for_user_id=for_user_id, effort=effort, now=now, tz=tz)
    )
    missions = zone_candidates(
        db, for_user_id=for_user_id, effort=effort, now=now, tz=tz
    )
    if missions:
        cards.insert(min(1, len(cards)), missions[0])
    return cards[:limit]


def compose_session(
    db: Session,
    *,
    for_user_id: int,
    minutes: int | None = None,
    room_id: int | None = None,
    effort: str | None = None,
    zone_id: int | None = None,
    exclude_ids: set[int] | None = None,
    now: datetime | None = None,
    tz: tzinfo | None = None,
) -> list[Task]:
    """A composed focus session (SPEC §5/§6, flag on): the greedy fill
    draws from the recurring lane, then AT MOST ONE current-zone mission
    joins when it fits the remaining budget — slotted into the queue by
    priority, never forced to position 1.

    `zone_id` is the repurposed Phase 4.6 home-screen zone scope:
    recurring work from that zone's rooms plus that zone's missions. The
    mission slot keeps the active-window gate, so scoping to an inactive
    zone simply means its rooms' recurring work — its missions wait for
    their week (working them early is the planning path, via
    zone_mission_session with an explicit zone_id). `room_id` scopes a
    room session the same way. `exclude_ids` keeps a timer-extend top-up
    from re-offering what's already queued."""
    from app.services import settings_service
    from app.services import zones as zone_service

    now = now or _utcnow()
    recurring = recurring_candidates(
        db,
        for_user_id=for_user_id,
        room_id=room_id,
        zone_id=zone_id,
        effort=effort,
        now=now,
        tz=tz,
    )
    missions = zone_candidates(
        db, for_user_id=for_user_id, effort=effort, now=now, tz=tz
    )
    if zone_id is not None and missions:
        local_tz = tz or settings_service.user_timezone(db, for_user_id)
        active = zone_service.zone_for_moment(db, now, local_tz)
        if active is None or active.id != zone_id:
            missions = []
    if room_id is not None:
        missions = [m for m in missions if m.room_id == room_id]
    if exclude_ids:
        recurring = [t for t in recurring if t.id not in exclude_ids]
        missions = [m for m in missions if m.id not in exclude_ids]

    if minutes is None:
        picked = recurring[:MAX_SESSION_TASKS]
    else:
        picked = _greedy_fill(recurring, minutes)

    if missions and len(picked) < MAX_SESSION_TASKS:
        if minutes is None:
            mission = missions[0]
        else:
            remaining = minutes - sum(t.estimated_minutes for t in picked)
            mission = next(
                (m for m in missions if m.estimated_minutes <= remaining), None
            )
        if mission is not None:
            score = priority_score(mission, now, tz)
            slot = next(
                (
                    i
                    for i, task in enumerate(picked)
                    if priority_score(task, now, tz) < score
                ),
                len(picked),
            )
            picked.insert(slot, mission)
    return picked


def zone_mission_session(
    db: Session,
    *,
    for_user_id: int,
    minutes: int | None = None,
    zone_id: int | None = None,
    effort: str | None = None,
    exclude_ids: set[int] | None = None,
    now: datetime | None = None,
    tz: tzinfo | None = None,
) -> list[Task]:
    """A zone session (SPEC §6, flag on): ONLY task_type='zone' missions,
    ranked by decay within the pool — no more dishes in a Kitchen Zone
    session. zone_id=None follows the automatic current-zone gate; an
    explicit zone_id is the planning path and works out of window. An
    empty pool is the surface's warm "this zone is feeling fresh"."""
    missions = zone_candidates(
        db, for_user_id=for_user_id, zone_id=zone_id, effort=effort, now=now, tz=tz
    )
    if exclude_ids:
        missions = [m for m in missions if m.id not in exclude_ids]
    if minutes is None:
        return missions[:MAX_SESSION_TASKS]
    return _greedy_fill(missions, minutes)


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
    return _greedy_fill(candidates, minutes)


def next_task_for_scope(
    db: Session,
    *,
    for_user_id: int,
    room_id: int | None = None,
    effort: str | None = None,
    now: datetime | None = None,
    tz: tzinfo | None = None,
) -> Task | None:
    """The single highest-priority task for a scope — the head of the very
    ranking every doing-surface uses (docs/hearth-integration.md gap #4:
    the Hearth wall shows ONE task at a time, SPEC D4). `room_id` scopes to
    a room (None = whole house); `for_user_id` is the acting adult, so her
    own and unassigned work surfaces while tasks delegated to someone else
    stay out.

    Dispatches exactly like routers/sessions.py, so Hearth's "next" is
    what the app itself would surface: with the Phase 11 lanes active, the
    composer path (out-of-window zone missions are never offered as debt);
    otherwise the legacy single-universe candidate path. Returns None when
    nothing is due — the calm rest state the wall shows instead of
    inventing work."""
    from app.services import settings_service

    now = now or _utcnow()
    if settings_service.lanes_active(db, for_user_id):
        if room_id is not None:
            tasks = compose_session(
                db,
                for_user_id=for_user_id,
                room_id=room_id,
                effort=effort,
                now=now,
                tz=tz,
            )
        else:
            tasks = compose_focus(
                db, limit=1, for_user_id=for_user_id, effort=effort, now=now, tz=tz
            )
    else:
        tasks = build_session(
            db,
            for_user_id=for_user_id,
            room_id=room_id,
            effort=effort,
            now=now,
            tz=tz,
        )
    return tasks[0] if tasks else None


def _local_week_start(now: datetime, tz: tzinfo | None) -> datetime:
    """Monday 00:00 in the member's local timezone (aware) — the fixed
    reset boundary for weekly chores. A chore done on or after it counts
    as done for this week; anything before it is due again."""
    local = now.astimezone(tz or timezone.utc)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - timedelta(days=local.weekday())  # weekday(): Monday = 0


def _chore_needs_doing(task: Task, now: datetime, week_start: datetime) -> bool:
    """Whether a chore is currently to-do. A weekly-cadence chore runs on
    the fixed Monday reset — not done since `week_start` means due, so it
    reappears every Monday and drops out the moment it's done that week.
    Every other chore uses the shared decay freshness gate."""
    if task.cadence_days == WEEKLY_CADENCE_DAYS:
        return task.last_done_at is None or _aware(task.last_done_at) < week_start
    return dirtiness_ratio(task, now) >= BAND_AGING


def _chores_eligible(
    tasks: list[Task], now: datetime, week_start: datetime
) -> list[Task]:
    """The chore-surface gate: the same resting fallback as
    `_doing_eligible` (snoozed chores surface only once nothing else is
    left), but weekly chores reset on the calendar week rather than on
    rolling decay (`_chore_needs_doing`)."""
    ready = [
        t
        for t in tasks
        if not is_snoozed(t, now) and _chore_needs_doing(t, now, week_start)
    ]
    if ready:
        return ready
    return [
        t
        for t in tasks
        if is_snoozed(t, now) and _chore_needs_doing(t, now, week_start)
    ]


def chores_for_user(
    db: Session, user_id: int, now: datetime | None = None, tz: tzinfo | None = None
) -> tuple[list[Task], list[Task]]:
    """The kid surface (SPEC §6 multi-user): (my chores, up for grabs),
    each priority-ranked.

    "My chores" = active tasks assigned to this member; "up for grabs" =
    active unassigned tasks the owner marked claimable. Assignment is
    explicit, so category isn't filtered here (an assigned maintenance job
    is still a chore) — but "up for grabs" is automatic surfacing, so
    projects stay out of it (issue #22): "project = manual only, NEVER
    automatic". Assigning a project to a kid IS the manual path, so an
    assigned one still lands in "my chores".

    Weekly-cadence chores reset on a fixed Monday (`_chore_needs_doing`):
    they reappear every Monday in the member's local week and drop out the
    moment they're done that week, instead of resurfacing ~3.5 days after
    each completion. Every other chore keeps the decay freshness gate, so
    it disappears once done and quietly returns when it needs doing again —
    same decay engine, no separate chore system.

    Each list applies the shared resting fallback (`_chores_eligible`)
    independently, so a resting chore surfaces once the rest of THAT list
    is caught up, without being crowded out by activity in the other."""
    now = now or _utcnow()
    week_start = _local_week_start(now, tz)
    tasks = db.scalars(
        select(Task).options(joinedload(Task.room)).where(Task.is_active.is_(True))
    ).all()
    mine = rank_tasks(
        _chores_eligible(
            [t for t in tasks if t.assignee_id == user_id], now, week_start
        ),
        now,
        tz,
    )
    up_for_grabs = rank_tasks(
        _chores_eligible(
            [
                t
                for t in tasks
                if t.assignee_id is None
                and t.claimable
                and t.task_type != "project"
            ],
            now,
            week_start,
        ),
        now,
        tz,
    )
    return mine, up_for_grabs


def room_aggregate_ratio(
    tasks: list[Task],
    now: datetime | None = None,
    ctx: "ZoneWindowContext | None" = None,
) -> float | None:
    """Room-level dirtiness (SPEC §4): a blend of the room's worst task and
    its average — "roughly the max/average" — so one overdue task colors
    the room without a single red drowning nine greens. None if the room
    has no active tasks.

    With a Phase 11 presentation context, out-of-window zone missions are
    excluded — a room never reads dirty because of work that isn't
    currently askable (SPEC §4 no-debt)."""
    now = now or _utcnow()
    ratios = [
        dirtiness_ratio(t, now)
        for t in tasks
        if t.is_active and in_zone_window(t, ctx)
    ]
    if not ratios:
        return None
    return 0.5 * max(ratios) + 0.5 * (sum(ratios) / len(ratios))


# ---------------------------------------------------------------------------
# The waiting state (Phase 11, SPEC §4) — presentation, never debt
#
# A zone mission's internal ratio keeps climbing while its zone is
# inactive; that state must never be shown as red/overdue. These helpers
# give the read layer just enough context to present an out-of-window
# mission as quietly waiting ("waits for Kitchen week") instead. Only the
# PRESENTATION changes — nothing here feeds selection or mutates state.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ZoneWindowContext:
    """What the read layer needs to present zone missions honestly: which
    zone window is open right now, Zone 3's extra room, and the names to
    say what a closed-window mission is waiting for."""

    active_zone_id: int | None
    week3_zone_id: int | None
    extra_room_id: int | None
    zone_names: dict[int, str]


def presentation_context(
    db: Session,
    for_user_id: int,
    now: datetime | None = None,
    tz: tzinfo | None = None,
) -> ZoneWindowContext | None:
    """None while the lanes are off — every band presents exactly as it
    always has (the permanent rollback boundary). With the lanes active,
    the context task_to_read and the room aggregates use to show
    out-of-window zone missions as quietly waiting."""
    from app.services import settings_service
    from app.services import zones as zone_service

    if not settings_service.lanes_active(db, for_user_id):
        return None
    now = now or _utcnow()
    local_tz = tz or settings_service.user_timezone(db, for_user_id)
    active = zone_service.zone_for_moment(db, now, local_tz)
    zones = list(db.scalars(select(Zone)).all())
    week3 = next((z for z in zones if z.week_of_month == 3), None)
    return ZoneWindowContext(
        active_zone_id=active.id if active else None,
        week3_zone_id=week3.id if week3 else None,
        extra_room_id=settings_service.zone_3_extra_room_id(db, for_user_id),
        zone_names={z.id: z.name for z in zones},
    )


def in_zone_window(task: Task, ctx: ZoneWindowContext | None) -> bool:
    """Whether this task's window is open right now. Non-zone tasks are
    always "in window" (the waiting state exists only for the zone lane),
    and without a context — lanes off — everything is. A mission with no
    room, or an unzoned room, has no window and waits until it's placed."""
    if ctx is None or task.task_type != "zone":
        return True
    room = task.room
    if room is None:
        return False
    if room.zone_id is not None and room.zone_id == ctx.active_zone_id:
        return True
    # Zone 3's extra room: in window while Zone 3's week is the open one.
    return (
        ctx.extra_room_id is not None
        and room.id == ctx.extra_room_id
        and ctx.week3_zone_id is not None
        and ctx.active_zone_id == ctx.week3_zone_id
    )


def window_zone_name(task: Task, ctx: ZoneWindowContext | None) -> str | None:
    """The zone whose week governs this mission — the name behind both
    the home card's "This week's Kitchen mission" label and the waiting
    copy ("waits for Kitchen week"). None for non-zone tasks, when the
    lanes are off, or when the mission has no zone to wait for."""
    if ctx is None or task.task_type != "zone" or task.room is None:
        return None
    room = task.room
    if room.zone_id is not None:
        return ctx.zone_names.get(room.zone_id)
    if ctx.extra_room_id == room.id and ctx.week3_zone_id is not None:
        return ctx.zone_names.get(ctx.week3_zone_id)
    return None


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
