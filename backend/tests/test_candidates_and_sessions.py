"""Tests for the query-backed lens functions (SPEC §6) and the session
builder (SPEC §5): candidate_tasks filters and build_session's greedy
time-budget fill. Runs against an in-memory SQLite session — the models
are compatible, and scheduling._aware() normalizes SQLite's naive
datetimes.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import Room, Zone
from app.services.scheduling import (
    MAX_SESSION_TASKS,
    build_session,
    candidate_tasks,
)

NOW = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)


def days_ago(days: float) -> datetime:
    return NOW - timedelta(days=days)


@pytest.fixture()
def add_task(db, make_task):
    """Persist a task; defaults to well overdue so it passes the
    freshness gate unless a test says otherwise."""

    def _add(**overrides):
        overrides.setdefault("cadence_days", 7)
        overrides.setdefault("last_done_at", days_ago(14))  # ratio 2.0
        task = make_task(**overrides)
        db.add(task)
        db.flush()
        return task

    return _add


# ---------------------------------------------------------------------------
# 7. candidate_tasks — each filter independently and in combination
# ---------------------------------------------------------------------------

class TestFreshnessGate:
    def test_fresh_tasks_are_excluded_and_the_boundary_is_inclusive(self, db, add_task):
        # The BAND_AGING gate: ratio >= 0.5 surfaces. Exactly 0.5 is in;
        # just under is out (cadence 100 keeps the math exact).
        fresh = add_task(name="fresh", cadence_days=100, last_done_at=days_ago(49))      # 0.49
        boundary = add_task(name="boundary", cadence_days=100, last_done_at=days_ago(50))  # 0.50
        dirty = add_task(name="dirty", cadence_days=100, last_done_at=days_ago(90))      # 0.90
        result = candidate_tasks(db, now=NOW)
        assert boundary in result and dirty in result
        assert fresh not in result

    def test_never_done_tasks_surface(self, db, add_task):
        never = add_task(name="never", last_done_at=None)
        assert never in candidate_tasks(db, now=NOW)

    def test_snoozed_tasks_are_hidden_until_expiry(self, db, add_task):
        snoozed = add_task(name="snoozed", snoozed_until=NOW + timedelta(hours=1))
        woken = add_task(name="woken", snoozed_until=NOW - timedelta(hours=1))
        result = candidate_tasks(db, now=NOW)
        assert snoozed not in result
        assert woken in result

    def test_inactive_tasks_are_excluded(self, db, add_task):
        retired = add_task(name="retired", is_active=False)
        assert retired not in candidate_tasks(db, now=NOW)

    def test_maintenance_tasks_are_excluded_from_cleaning_surfaces(self, db, add_task):
        # SPEC §6: maintenance lives in its own section/filter so it never
        # clutters daily cleaning — the lens only serves category "cleaning".
        furnace = add_task(name="furnace filter", category="maintenance")
        assert furnace not in candidate_tasks(db, now=NOW)


class TestLensFilters:
    def test_room_filter(self, db, add_task):
        kitchen = Room(name="Kitchen")
        office = Room(name="Office")
        db.add_all([kitchen, office])
        db.flush()
        counters = add_task(name="counters", room_id=kitchen.id)
        desk = add_task(name="desk", room_id=office.id)
        homeless = add_task(name="no room", room_id=None)
        result = candidate_tasks(db, room_id=kitchen.id, now=NOW)
        assert result == [counters]
        assert desk not in result and homeless not in result

    def test_zone_filter(self, db, add_task):
        zone = Zone(name="Zone 2", week_of_month=2)
        db.add(zone)
        db.flush()
        kitchen = Room(name="Kitchen", zone_id=zone.id)
        office = Room(name="Office", zone_id=None)
        db.add_all([kitchen, office])
        db.flush()
        counters = add_task(name="counters", room_id=kitchen.id)
        desk = add_task(name="desk", room_id=office.id)
        roomless = add_task(name="no room", room_id=None)
        result = candidate_tasks(db, zone_id=zone.id, now=NOW)
        assert result == [counters]
        assert desk not in result and roomless not in result

    def test_effort_filter(self, db, add_task):
        quick = add_task(name="quick", effort="quick")
        deep = add_task(name="deep", effort="deep")
        assert candidate_tasks(db, effort="quick", now=NOW) == [quick]
        assert candidate_tasks(db, effort="deep", now=NOW) == [deep]

    def test_effort_filter_ignores_unknown_values(self, db, add_task):
        # Only "quick"/"deep" filter; None or junk means no effort filter.
        quick = add_task(name="quick", effort="quick")
        deep = add_task(name="deep", effort="deep")
        assert set(candidate_tasks(db, now=NOW)) == {quick, deep}
        assert set(candidate_tasks(db, effort="all", now=NOW)) == {quick, deep}

    def test_guest_only_is_guest_facing_and_quick(self, db, add_task):
        # Chaos Cleaning (SPEC §6): with company coming the win is fast
        # visible impact — guest-facing AND quick, deep work skipped.
        punch = add_task(name="fluff pillows", guest_facing=True, effort="quick")
        deep_guest = add_task(name="shampoo carpet", guest_facing=True, effort="deep")
        hidden = add_task(name="sort closet", guest_facing=False, effort="quick")
        result = candidate_tasks(db, guest_only=True, now=NOW)
        assert result == [punch]
        assert deep_guest not in result and hidden not in result

    def test_for_user_excludes_tasks_delegated_to_others(self, db, add_task, owner, kid):
        # Her own and unassigned tasks surface; work assigned to a
        # different member never nags her (SPEC §6).
        mine = add_task(name="mine", assignee_id=owner.id)
        unassigned = add_task(name="unassigned", assignee_id=None)
        delegated = add_task(name="kid's chore", assignee_id=kid.id)
        result = candidate_tasks(db, for_user_id=owner.id, now=NOW)
        assert set(result) == {mine, unassigned}
        assert delegated not in result

    def test_without_for_user_no_assignee_filter_applies(self, db, add_task, kid):
        delegated = add_task(name="kid's chore", assignee_id=kid.id)
        assert delegated in candidate_tasks(db, now=NOW)

    def test_filters_combine(self, db, add_task, owner, kid):
        kitchen = Room(name="Kitchen")
        office = Room(name="Office")
        db.add_all([kitchen, office])
        db.flush()
        match = add_task(name="match", room_id=kitchen.id, effort="quick", assignee_id=None)
        wrong_room = add_task(name="wrong room", room_id=office.id, effort="quick")
        wrong_effort = add_task(name="wrong effort", room_id=kitchen.id, effort="deep")
        delegated = add_task(
            name="delegated", room_id=kitchen.id, effort="quick", assignee_id=kid.id
        )
        too_fresh = add_task(
            name="too fresh", room_id=kitchen.id, effort="quick", last_done_at=days_ago(1)
        )
        result = candidate_tasks(
            db, room_id=kitchen.id, effort="quick", for_user_id=owner.id, now=NOW
        )
        assert result == [match]
        assert {wrong_room, wrong_effort, delegated, too_fresh}.isdisjoint(result)

    def test_results_come_back_priority_ranked(self, db, add_task):
        aging = add_task(name="aging", last_done_at=days_ago(4.2))    # 0.6
        overdue = add_task(name="overdue", last_done_at=days_ago(14))  # 2.0
        due = add_task(name="due", last_done_at=days_ago(7))           # 1.0
        assert candidate_tasks(db, now=NOW) == [overdue, due, aging]


# ---------------------------------------------------------------------------
# 8. build_session — the greedy time-budget fill
# ---------------------------------------------------------------------------

class TestBuildSession:
    def test_greedy_fill_takes_highest_priority_first_within_budget(self, db, add_task):
        # Priority order a > b > c > d. Budget 30: a (20) fits, b (15) no
        # longer does, c (10) fills the rest, d (5) finds nothing left.
        a = add_task(name="a", last_done_at=days_ago(21), estimated_minutes=20)    # 3.0
        b = add_task(name="b", last_done_at=days_ago(17.5), estimated_minutes=15)  # 2.5
        c = add_task(name="c", last_done_at=days_ago(14), estimated_minutes=10)    # 2.0
        d = add_task(name="d", last_done_at=days_ago(10.5), estimated_minutes=5)   # 1.5
        session = build_session(db, minutes=30, now=NOW)
        assert session == [a, c]
        assert sum(t.estimated_minutes for t in session) <= 30

    def test_budget_is_never_exceeded(self, db, add_task):
        for i in range(6):
            add_task(name=f"t{i}", estimated_minutes=10)
        session = build_session(db, minutes=35, now=NOW)
        assert sum(t.estimated_minutes for t in session) <= 35
        assert len(session) == 3  # 3 × 10 fits; a 4th would overshoot

    def test_a_task_too_big_for_the_whole_budget_is_skipped(self, db, add_task):
        marathon = add_task(name="marathon", last_done_at=days_ago(21), estimated_minutes=60)
        quickie = add_task(name="quickie", last_done_at=days_ago(7), estimated_minutes=10)
        session = build_session(db, minutes=15, now=NOW)
        assert session == [quickie]
        assert marathon not in session

    def test_session_caps_at_max_session_tasks_with_budget(self, db, add_task):
        for i in range(MAX_SESSION_TASKS + 2):
            add_task(name=f"t{i}", estimated_minutes=5)
        session = build_session(db, minutes=120, now=NOW)
        assert len(session) == MAX_SESSION_TASKS

    def test_no_budget_room_session_returns_priority_order(self, db, add_task):
        # Picking a room without a time budget: the room's non-fresh tasks
        # in priority order, still capped.
        room = Room(name="Kitchen")
        db.add(room)
        db.flush()
        mild = add_task(name="mild", room_id=room.id, last_done_at=days_ago(4.2))   # 0.6
        worst = add_task(name="worst", room_id=room.id, last_done_at=days_ago(14))  # 2.0
        mid = add_task(name="mid", room_id=room.id, last_done_at=days_ago(7))       # 1.0
        elsewhere = add_task(name="elsewhere", room_id=None)
        session = build_session(db, room_id=room.id, now=NOW)
        assert session == [worst, mid, mild]
        assert elsewhere not in session

    def test_no_budget_session_still_caps_at_max_session_tasks(self, db, add_task):
        room = Room(name="Everything")
        db.add(room)
        db.flush()
        for i in range(MAX_SESSION_TASKS + 2):
            add_task(name=f"t{i}", room_id=room.id)
        assert len(build_session(db, room_id=room.id, now=NOW)) == MAX_SESSION_TASKS

    def test_exclude_ids_keeps_queued_tasks_out_of_a_top_up(self, db, add_task):
        # The Phase 5 timer-extend: tasks already in her running queue are
        # never re-offered.
        a = add_task(name="a", last_done_at=days_ago(21), estimated_minutes=10)   # 3.0
        b = add_task(name="b", last_done_at=days_ago(14), estimated_minutes=10)   # 2.0
        c = add_task(name="c", last_done_at=days_ago(10.5), estimated_minutes=10)  # 1.5
        session = build_session(db, minutes=20, exclude_ids={a.id}, now=NOW)
        assert session == [b, c]


# ---------------------------------------------------------------------------
# Preferred-day boost (Phase 8) — end to end through the session builder
# ---------------------------------------------------------------------------

class TestPreferredDayInSessions:
    def test_saturday_laundry_leads_a_saturday_session(self, db, add_task):
        # Saturday noon UTC. Boosted laundry (1.0 + 2.0) jumps a dirtier
        # ordinary task (2.0) — and the boost rides through candidate
        # ranking and the greedy fill untouched.
        saturday = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
        assert saturday.weekday() == 5
        laundry = add_task(
            name="laundry",
            preferred_day=5,
            last_done_at=saturday - timedelta(days=7),   # 1.0
        )
        bathroom = add_task(
            name="bathroom",
            last_done_at=saturday - timedelta(days=14),  # 2.0
        )
        assert candidate_tasks(db, now=saturday) == [laundry, bathroom]
        assert build_session(db, minutes=30, now=saturday) == [laundry, bathroom]
        # Midweek the same pair falls back to plain decay order.
        wednesday = saturday + timedelta(days=4)
        assert candidate_tasks(db, now=wednesday)[0] is bathroom
