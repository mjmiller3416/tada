"""Tests for the Phase 10 scheduling lanes (SPEC §4): the separated
selectors (recurring_candidates / zone_candidates / project_candidates),
the no-debt rule, the shared completion path, and the regression guard
that pins the legacy candidate_tasks path to its pre-Phase-10 behavior
while the zone_lane_enabled flag ships off.

July 2026 starts on a Wednesday, so its Monday–Sunday zone weeks are:
week 1 = Jul 1–5, week 2 = Jul 6–12 (Kitchen here), week 3 = Jul 13–19,
week 4 = Jul 20–26 (Bedroom here), week 5 = Jul 27–31. August 2026's
week 2 runs Aug 3–9 — the "zone comes round again" moment.

The owner fixture pins her timezone to UTC so zone weeks line up exactly
with the UTC timestamps below.
"""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.models import Badge, CompletionLog, Reminder, Room, Setting, UserBadge, Zone
from app.services import settings_service
from app.services.scheduling import (
    band_for_ratio,
    build_session,
    candidate_tasks,
    complete_task,
    daily_focus,
    dirtiness_ratio,
    project_candidates,
    recurring_candidates,
    undo_completion,
    zone_candidates,
)

KITCHEN_WEEK = datetime(2026, 7, 8, 12, 0, 0, tzinfo=timezone.utc)        # week 2
KITCHEN_WEEK_STARTS = datetime(2026, 7, 6, 0, 0, 1, tzinfo=timezone.utc)  # Mon 00:00:01
BEDROOM_WEEK = datetime(2026, 7, 22, 12, 0, 0, tzinfo=timezone.utc)       # week 4
NEXT_KITCHEN_WEEK = datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone.utc)   # Aug, week 2


@pytest.fixture()
def home(db):
    """Two zoned rooms: the Kitchen in the week-2 zone, the Bedroom in
    the week-4 zone."""
    kitchen_zone = Zone(name="Kitchen", week_of_month=2, sort_order=2)
    bedroom_zone = Zone(name="Master bedroom", week_of_month=4, sort_order=4)
    db.add_all([kitchen_zone, bedroom_zone])
    db.flush()
    kitchen = Room(name="Kitchen", zone_id=kitchen_zone.id)
    bedroom = Room(name="Bedroom", zone_id=bedroom_zone.id)
    db.add_all([kitchen, bedroom])
    db.flush()
    return SimpleNamespace(
        kitchen=kitchen,
        bedroom=bedroom,
        kitchen_zone=kitchen_zone,
        bedroom_zone=bedroom_zone,
    )


@pytest.fixture()
def zones_on(db, owner):
    """The Phase 3 zones overlay, switched on for the owner."""
    db.add(Setting(user_id=owner.id, key="zones_enabled", value="true"))
    db.flush()


@pytest.fixture()
def add_task(db, make_task):
    """Persist a task; defaults to well overdue at KITCHEN_WEEK (and
    still overdue at every other moment used here)."""

    def _add(**overrides):
        overrides.setdefault("cadence_days", 7)
        overrides.setdefault("last_done_at", KITCHEN_WEEK - timedelta(days=14))
        task = make_task(**overrides)
        db.add(task)
        db.flush()
        return task

    return _add


# ---------------------------------------------------------------------------
# Eligibility — each lane sees only its own work
# ---------------------------------------------------------------------------

class TestLaneEligibility:
    def test_routine_kitchen_task_stays_recurring_during_bedroom_week(
        self, db, add_task, owner, home, zones_on
    ):
        # Routines continue everywhere regardless of the active zone —
        # zone work is additional attention, never a replacement.
        dishes = add_task(name="Do the dishes", room_id=home.kitchen.id)
        assert dishes in recurring_candidates(db, now=BEDROOM_WEEK)

    def test_kitchen_mission_is_absent_during_bedroom_week(
        self, db, add_task, owner, home, zones_on
    ):
        oven = add_task(
            name="Deep-clean the oven", room_id=home.kitchen.id, task_type="zone"
        )
        assert oven not in zone_candidates(db, for_user_id=owner.id, now=BEDROOM_WEEK)

    def test_the_same_mission_appears_during_kitchen_week(
        self, db, add_task, owner, home, zones_on
    ):
        oven = add_task(
            name="Deep-clean the oven", room_id=home.kitchen.id, task_type="zone"
        )
        assert oven in zone_candidates(db, for_user_id=owner.id, now=KITCHEN_WEEK)

    def test_bedroom_mission_drops_out_the_moment_kitchen_week_begins(
        self, db, add_task, owner, home, zones_on
    ):
        drawer = add_task(
            name="Declutter one drawer", room_id=home.bedroom.id, task_type="zone"
        )
        shelf = add_task(
            name="Clean one refrigerator shelf",
            room_id=home.kitchen.id,
            task_type="zone",
        )
        during_bedroom = zone_candidates(db, for_user_id=owner.id, now=BEDROOM_WEEK)
        assert drawer in during_bedroom and shelf not in during_bedroom
        at_flip = zone_candidates(db, for_user_id=owner.id, now=KITCHEN_WEEK_STARTS)
        assert shelf in at_flip and drawer not in at_flip

    def test_one_room_holds_both_lanes_and_each_sees_only_its_own(
        self, db, add_task, owner, home, zones_on
    ):
        dishes = add_task(name="Do the dishes", room_id=home.kitchen.id)
        microwave = add_task(
            name="Clean the microwave", room_id=home.kitchen.id, task_type="zone"
        )
        recurring = recurring_candidates(db, now=KITCHEN_WEEK)
        missions = zone_candidates(db, for_user_id=owner.id, now=KITCHEN_WEEK)
        assert dishes in recurring and microwave not in recurring
        assert microwave in missions and dishes not in missions

    def test_zone_candidates_returns_nothing_when_the_overlay_is_off(
        self, db, add_task, owner, home
    ):
        # No zones_on fixture: automatic selection respects the Phase 3
        # opt-in — off means pure global decay, cleanly.
        add_task(name="Clean the microwave", room_id=home.kitchen.id, task_type="zone")
        assert zone_candidates(db, for_user_id=owner.id, now=KITCHEN_WEEK) == []

    def test_projects_appear_in_no_automatic_selector(
        self, db, add_task, owner, home, zones_on
    ):
        closet = add_task(
            name="Reorganize the closet", room_id=home.kitchen.id, task_type="project"
        )
        assert closet not in recurring_candidates(db, now=KITCHEN_WEEK)
        assert closet not in zone_candidates(db, for_user_id=owner.id, now=KITCHEN_WEEK)
        # Calling the manual lane IS the explicit request.
        assert closet in project_candidates(db, now=KITCHEN_WEEK)

    def test_explicit_zone_id_still_retrieves_an_inactive_zones_missions(
        self, db, add_task, owner, home
    ):
        # The planning path: asking for a specific zone is the opt-in, so
        # it works out of window and without the overlay setting.
        oven = add_task(
            name="Deep-clean the oven", room_id=home.kitchen.id, task_type="zone"
        )
        result = zone_candidates(
            db, for_user_id=owner.id, zone_id=home.kitchen_zone.id, now=BEDROOM_WEEK
        )
        assert result == [oven]

    def test_the_energy_filter_applies_to_the_zone_pool_too(
        self, db, add_task, owner, home, zones_on
    ):
        # SPEC §6: low-energy days deserve low-energy missions too.
        shelf = add_task(
            name="Clean one refrigerator shelf",
            room_id=home.kitchen.id,
            task_type="zone",
            effort="quick",
        )
        oven = add_task(
            name="Deep-clean the oven",
            room_id=home.kitchen.id,
            task_type="zone",
            effort="deep",
        )
        result = zone_candidates(
            db, for_user_id=owner.id, effort="quick", now=KITCHEN_WEEK
        )
        assert shelf in result and oven not in result

    def test_missions_delegated_to_someone_else_stay_off_her_pool(
        self, db, add_task, owner, kid, home, zones_on
    ):
        chore = add_task(
            name="Wipe cabinet fronts",
            room_id=home.kitchen.id,
            task_type="zone",
            assignee_id=kid.id,
        )
        assert chore not in zone_candidates(db, for_user_id=owner.id, now=KITCHEN_WEEK)

    def test_maintenance_rides_the_recurring_lane(self, db, add_task, owner):
        # SPEC §4 lanes: maintenance is decay-scheduled (long cadences) —
        # it belongs to recurring_candidates; Phase 11's composer decides
        # what each surface shows.
        furnace = add_task(name="Change the furnace filter", task_type="maintenance")
        assert furnace in recurring_candidates(db, now=KITCHEN_WEEK)


# ---------------------------------------------------------------------------
# The no-debt rule — rollover is pure non-selection
# ---------------------------------------------------------------------------

class TestNoDebt:
    def _counts(self, db) -> tuple[int, int]:
        logs = db.scalar(select(func.count(CompletionLog.id))) or 0
        reminders = db.scalar(select(func.count(Reminder.id))) or 0
        return logs, reminders

    def test_rollover_writes_nothing_and_mutates_no_task_state(
        self, db, add_task, owner, home, zones_on
    ):
        last_done = KITCHEN_WEEK - timedelta(days=14)
        oven = add_task(
            name="Deep-clean the oven",
            room_id=home.kitchen.id,
            task_type="zone",
            last_done_at=last_done,
        )
        assert oven in zone_candidates(db, for_user_id=owner.id, now=KITCHEN_WEEK)
        # The week turns. Nothing happens to the task — it just stops
        # being selected.
        assert oven not in zone_candidates(db, for_user_id=owner.id, now=BEDROOM_WEEK)
        assert self._counts(db) == (0, 0)
        assert oven.last_done_at == last_done
        assert oven.snoozed_until is None
        assert oven.is_active is True
        assert oven.task_type == "zone"

    def test_a_ratio_three_mission_out_of_window_is_simply_ineligible(
        self, db, add_task, owner, home, zones_on
    ):
        oven = add_task(
            name="Deep-clean the oven",
            room_id=home.kitchen.id,
            task_type="zone",
            cadence_days=7,
            last_done_at=BEDROOM_WEEK - timedelta(days=21),  # ratio 3.0
        )
        assert dirtiness_ratio(oven, BEDROOM_WEEK) == 3.0
        assert oven not in zone_candidates(db, for_user_id=owner.id, now=BEDROOM_WEEK)
        # Nothing else: the ratio keeps quietly climbing, unreset.
        assert dirtiness_ratio(oven, BEDROOM_WEEK) == 3.0
        assert self._counts(db) == (0, 0)

    def test_when_the_zone_returns_the_mission_is_eligible_with_history_intact(
        self, db, add_task, owner, home, zones_on
    ):
        last_done = KITCHEN_WEEK - timedelta(days=14)
        oven = add_task(
            name="Deep-clean the oven",
            room_id=home.kitchen.id,
            task_type="zone",
            last_done_at=last_done,
        )
        assert oven not in zone_candidates(db, for_user_id=owner.id, now=BEDROOM_WEEK)
        back_again = zone_candidates(db, for_user_id=owner.id, now=NEXT_KITCHEN_WEEK)
        assert oven in back_again
        assert oven.last_done_at == last_done  # history intact, no reset


# ---------------------------------------------------------------------------
# Completion path — one seam for every lane
# ---------------------------------------------------------------------------

class TestZoneCompletionPath:
    def test_completing_a_mission_feeds_the_log_streak_and_badges_identically(
        self, db, add_task, owner, home
    ):
        oven = add_task(
            name="Deep-clean the oven", room_id=home.kitchen.id, task_type="zone"
        )
        log = complete_task(db, oven, owner, "zone", KITCHEN_WEEK)
        assert oven.last_done_at == KITCHEN_WEEK
        assert log.source == "zone"
        assert owner.current_streak == 1
        assert owner.last_active_date == date(2026, 7, 8)
        first_task = db.scalar(select(Badge).where(Badge.code == "first_task"))
        earned = db.scalar(
            select(UserBadge).where(
                UserBadge.user_id == owner.id, UserBadge.badge_id == first_task.id
            )
        )
        assert earned is not None

    def test_undo_round_trip_on_a_zone_mission(self, db, add_task, owner, home):
        # The Phase 9 test that matters most, repeated on the new type:
        # complete + undo returns the mission to exactly the priority it
        # had, as if the mis-tap never happened.
        oven = add_task(
            name="Deep-clean the oven",
            room_id=home.kitchen.id,
            task_type="zone",
            last_done_at=KITCHEN_WEEK - timedelta(days=10),
        )
        before_ratio = dirtiness_ratio(oven, KITCHEN_WEEK)
        before_band = band_for_ratio(before_ratio)
        log = complete_task(db, oven, owner, "zone", KITCHEN_WEEK)
        undo_completion(db, log, KITCHEN_WEEK)
        assert dirtiness_ratio(oven, KITCHEN_WEEK) == before_ratio
        assert band_for_ratio(dirtiness_ratio(oven, KITCHEN_WEEK)) == before_band


# ---------------------------------------------------------------------------
# Regression guard — with the flag off, the legacy path is untouched
# ---------------------------------------------------------------------------

class TestLegacyPathUnchanged:
    """Phase 10's acceptance bar: after deploy, the app behaves exactly
    as it did the day before. candidate_tasks/daily_focus/build_session
    must keep ranking on decay alone, blind to the new types (except the
    maintenance exclusion they always had via the old category column)."""

    def test_the_zone_lane_flag_ships_off(self, db, owner):
        assert settings_service.zone_lane_enabled(db, owner.id) is False

    def _mixed_home(self, add_task, home):
        # Distinct ratios so the expected pure-decay order is unambiguous.
        mission = add_task(
            name="Deep-clean the oven",
            room_id=home.kitchen.id,
            task_type="zone",
            last_done_at=BEDROOM_WEEK - timedelta(days=21),  # 3.0
            estimated_minutes=20,
        )
        routine = add_task(
            name="Do the dishes",
            room_id=home.kitchen.id,
            task_type="routine",
            last_done_at=BEDROOM_WEEK - timedelta(days=14),  # 2.0
            estimated_minutes=10,
        )
        blessing = add_task(
            name="Vacuum the floor",
            room_id=home.bedroom.id,
            task_type="weekly_blessing",
            last_done_at=BEDROOM_WEEK - timedelta(days=10.5),  # 1.5
            estimated_minutes=5,
        )
        maintenance = add_task(
            name="Change the furnace filter",
            task_type="maintenance",
            last_done_at=BEDROOM_WEEK - timedelta(days=14),
        )
        return mission, routine, blessing, maintenance

    def test_candidate_tasks_ranks_on_decay_alone_blind_to_types(
        self, db, add_task, owner, home, zones_on
    ):
        # It is BEDROOM week, and the kitchen mission still surfaces
        # globally at full priority — the Phase 3 behavior, deliberately
        # preserved until Phase 11 flips the flag. Only maintenance is
        # excluded, exactly as the old category filter did.
        mission, routine, blessing, maintenance = self._mixed_home(add_task, home)
        assert candidate_tasks(db, now=BEDROOM_WEEK) == [mission, routine, blessing]
        assert maintenance not in candidate_tasks(db, now=BEDROOM_WEEK)

    def test_daily_focus_still_serves_out_of_window_missions(
        self, db, add_task, owner, home, zones_on
    ):
        mission, routine, blessing, _ = self._mixed_home(add_task, home)
        assert daily_focus(db, limit=3, now=BEDROOM_WEEK) == [
            mission,
            routine,
            blessing,
        ]

    def test_build_session_greedy_fill_is_unchanged(
        self, db, add_task, owner, home, zones_on
    ):
        # Budget 25: the mission (20) fits, the routine (10) no longer
        # does, the blessing (5) fills the rest — types never consulted.
        mission, routine, blessing, _ = self._mixed_home(add_task, home)
        session = build_session(db, minutes=25, now=BEDROOM_WEEK)
        assert session == [mission, blessing]
        assert routine not in session

    def test_the_zone_room_filter_still_serves_every_type_in_the_room(
        self, db, add_task, owner, home, zones_on
    ):
        # The Phase 3 zone_id lens on candidate_tasks stays a plain room
        # filter (dishes and all) until Phase 11 repurposes the surface.
        mission, routine, _, _ = self._mixed_home(add_task, home)
        result = candidate_tasks(db, zone_id=home.kitchen_zone.id, now=BEDROOM_WEEK)
        assert result == [mission, routine]
