"""Tests for the Phase 11 composer and zone surfaces (SPEC §4/§5/§6):
compose_focus's routine/mission/routine cards, the composed timed
session's single slotted mission, mission-only zone sessions, the
routines-only guest filter, the lanes_active gate, Zone 3's rotating
extra room, and the waiting-state presentation.

Same calendar as test_lane_selectors: July 2026 starts on a Wednesday,
so its Monday–Sunday zone weeks are week 1 = Jul 1–5, week 2 = Jul 6–12
(Kitchen here), week 3 = Jul 13–19 (Bathroom here), week 4 = Jul 20–26
(Bedroom here). Saturday Jul 11 falls inside Kitchen week — the
preferred-day / mission interplay moment. The owner fixture pins her
timezone to UTC so zone weeks line up exactly with these timestamps.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models import Room, Setting, Zone
from app.schemas.tasks import task_to_read
from app.services import settings_service
from app.services.scheduling import (
    band_for_ratio,
    build_session,
    candidate_tasks,
    compose_focus,
    compose_session,
    daily_focus,
    dirtiness_ratio,
    in_zone_window,
    presentation_context,
    room_aggregate_ratio,
    window_zone_name,
    zone_candidates,
    zone_mission_session,
)

KITCHEN_WEEK = datetime(2026, 7, 8, 12, 0, 0, tzinfo=timezone.utc)     # week 2
SATURDAY = datetime(2026, 7, 11, 12, 0, 0, tzinfo=timezone.utc)        # week 2, Sat
BATHROOM_WEEK = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)   # week 3
BEDROOM_WEEK = datetime(2026, 7, 22, 12, 0, 0, tzinfo=timezone.utc)    # week 4


@pytest.fixture()
def home(db):
    """Three zoned rooms (Kitchen week 2, Bathroom week 3, Bedroom week
    4) plus an unzoned craft room — Zone 3's rotating-extra candidate."""
    kitchen_zone = Zone(name="Kitchen", week_of_month=2, sort_order=2)
    bathroom_zone = Zone(name="Bathroom", week_of_month=3, sort_order=3)
    bedroom_zone = Zone(name="Master bedroom", week_of_month=4, sort_order=4)
    db.add_all([kitchen_zone, bathroom_zone, bedroom_zone])
    db.flush()
    kitchen = Room(name="Kitchen", zone_id=kitchen_zone.id)
    bathroom = Room(name="Bathroom", zone_id=bathroom_zone.id)
    bedroom = Room(name="Bedroom", zone_id=bedroom_zone.id)
    craft = Room(name="Craft room", zone_id=None)
    db.add_all([kitchen, bathroom, bedroom, craft])
    db.flush()
    return SimpleNamespace(
        kitchen=kitchen,
        bathroom=bathroom,
        bedroom=bedroom,
        craft=craft,
        kitchen_zone=kitchen_zone,
        bathroom_zone=bathroom_zone,
        bedroom_zone=bedroom_zone,
    )


@pytest.fixture()
def zones_on(db, owner):
    db.add(Setting(user_id=owner.id, key="zones_enabled", value="true"))
    db.flush()


@pytest.fixture()
def lane_on(db, owner):
    """The Phase 10 flag, flipped — with zones_on, the lanes are live."""
    db.add(Setting(user_id=owner.id, key="zone_lane_enabled", value="true"))
    db.flush()


@pytest.fixture()
def add_task(db, make_task):
    """Persist a task; defaults to well overdue at every moment used
    here (ratio 2.0 at KITCHEN_WEEK)."""

    def _add(**overrides):
        overrides.setdefault("cadence_days", 7)
        overrides.setdefault("last_done_at", KITCHEN_WEEK - timedelta(days=14))
        task = make_task(**overrides)
        db.add(task)
        db.flush()
        return task

    return _add


# ---------------------------------------------------------------------------
# compose_focus — routine / mission / routine, never a wall
# ---------------------------------------------------------------------------

class TestComposeFocus:
    def test_composes_routine_mission_routine(self, db, add_task, owner, home, zones_on):
        dishes = add_task(
            name="Do the dishes",
            room_id=home.kitchen.id,
            last_done_at=KITCHEN_WEEK - timedelta(days=21),  # ratio 3.0
        )
        counters = add_task(
            name="Wipe down the counters",
            room_id=home.kitchen.id,
            last_done_at=KITCHEN_WEEK - timedelta(days=14),  # ratio 2.0
        )
        microwave = add_task(
            name="Clean the microwave", room_id=home.kitchen.id, task_type="zone"
        )
        cards = compose_focus(db, limit=3, for_user_id=owner.id, now=KITCHEN_WEEK)
        assert cards == [dishes, microwave, counters]

    def test_no_eligible_mission_falls_back_to_recurring(
        self, db, add_task, owner, home, zones_on
    ):
        # It is Kitchen week, but the only mission belongs to the bedroom
        # — the slot quietly becomes another recurring card, never empty.
        first = add_task(name="Do the dishes", room_id=home.kitchen.id,
                         last_done_at=KITCHEN_WEEK - timedelta(days=28))
        second = add_task(name="Wipe down the counters", room_id=home.kitchen.id,
                          last_done_at=KITCHEN_WEEK - timedelta(days=21))
        third = add_task(name="Sweep the floor", room_id=home.kitchen.id,
                         last_done_at=KITCHEN_WEEK - timedelta(days=14))
        add_task(
            name="Declutter one drawer", room_id=home.bedroom.id, task_type="zone"
        )
        cards = compose_focus(db, limit=3, for_user_id=owner.id, now=KITCHEN_WEEK)
        assert cards == [first, second, third]

    def test_daily_focus_count_still_caps_the_total(
        self, db, add_task, owner, home, zones_on
    ):
        dishes = add_task(
            name="Do the dishes",
            room_id=home.kitchen.id,
            last_done_at=KITCHEN_WEEK - timedelta(days=21),
        )
        add_task(name="Wipe down the counters", room_id=home.kitchen.id)
        microwave = add_task(
            name="Clean the microwave", room_id=home.kitchen.id, task_type="zone"
        )
        cards = compose_focus(db, limit=2, for_user_id=owner.id, now=KITCHEN_WEEK)
        assert cards == [dishes, microwave]

    def test_mission_alone_still_makes_a_card(self, db, add_task, owner, home, zones_on):
        microwave = add_task(
            name="Clean the microwave", room_id=home.kitchen.id, task_type="zone"
        )
        cards = compose_focus(db, limit=3, for_user_id=owner.id, now=KITCHEN_WEEK)
        assert cards == [microwave]

    def test_energy_filter_applies_to_both_pools(
        self, db, add_task, owner, home, zones_on
    ):
        quick_routine = add_task(
            name="Wipe down the counters", room_id=home.kitchen.id, effort="quick"
        )
        deep_routine = add_task(
            name="Scrub the floors", room_id=home.kitchen.id, effort="deep",
            last_done_at=KITCHEN_WEEK - timedelta(days=21),
        )
        quick_mission = add_task(
            name="Clean one refrigerator shelf",
            room_id=home.kitchen.id,
            task_type="zone",
            effort="quick",
        )
        deep_mission = add_task(
            name="Deep-clean the oven", room_id=home.kitchen.id,
            task_type="zone", effort="deep",
        )
        cards = compose_focus(
            db, limit=3, for_user_id=owner.id, effort="quick", now=KITCHEN_WEEK
        )
        assert cards == [quick_routine, quick_mission]
        assert deep_routine not in cards and deep_mission not in cards

    def test_saturday_blessing_and_mission_compose_in_pinned_order(
        self, db, add_task, owner, home, zones_on
    ):
        # The three boosts/gates interacting: a Saturday-preferred weekly
        # blessing (score 1.0 + 2.0 boost = 3.0) leads, the Kitchen-week
        # mission holds card 2 by composition (not by score), and the
        # plain routine (ratio 2.0) follows. Pinned explicitly — this is
        # where regressions would hide.
        blessing = add_task(
            name="Vacuum the floor",
            room_id=home.kitchen.id,
            task_type="weekly_blessing",
            preferred_day=5,  # Saturday
            last_done_at=SATURDAY - timedelta(days=7),  # ratio 1.0
        )
        routine = add_task(
            name="Do the dishes",
            room_id=home.kitchen.id,
            last_done_at=SATURDAY - timedelta(days=14),  # ratio 2.0
        )
        mission = add_task(
            name="Clean the microwave",
            room_id=home.kitchen.id,
            task_type="zone",
            last_done_at=SATURDAY - timedelta(days=28),  # ratio 4.0 — still card 2
        )
        cards = compose_focus(db, limit=3, for_user_id=owner.id, now=SATURDAY)
        assert cards == [blessing, mission, routine]


# ---------------------------------------------------------------------------
# compose_session — at most one mission, slotted by priority
# ---------------------------------------------------------------------------

class TestComposeSession:
    def test_one_mission_joins_slotted_by_priority_never_position_one(
        self, db, add_task, owner, home, zones_on
    ):
        r1 = add_task(
            name="Do the dishes", room_id=home.kitchen.id, estimated_minutes=10,
            last_done_at=KITCHEN_WEEK - timedelta(days=21),  # 3.0
        )
        r2 = add_task(
            name="Wipe down the counters", room_id=home.kitchen.id, estimated_minutes=10,
            last_done_at=KITCHEN_WEEK - timedelta(days=14),  # 2.0
        )
        m1 = add_task(
            name="Clean the microwave", room_id=home.kitchen.id, task_type="zone",
            estimated_minutes=10,
            last_done_at=KITCHEN_WEEK - timedelta(days=17.5),  # 2.5
        )
        m2 = add_task(
            name="Wipe cabinet fronts", room_id=home.kitchen.id, task_type="zone",
            estimated_minutes=5,
            last_done_at=KITCHEN_WEEK - timedelta(days=16),
        )
        session = compose_session(
            db, for_user_id=owner.id, minutes=30, now=KITCHEN_WEEK
        )
        # The recurring fill takes r1+r2, the top mission fits the
        # remaining 10 and slots BETWEEN them by priority; only one
        # mission ever joins.
        assert session == [r1, m1, r2]
        assert m2 not in session

    def test_mission_that_does_not_fit_stays_out(
        self, db, add_task, owner, home, zones_on
    ):
        r1 = add_task(
            name="Do the dishes", room_id=home.kitchen.id, estimated_minutes=10,
            last_done_at=KITCHEN_WEEK - timedelta(days=21),
        )
        r2 = add_task(
            name="Wipe down the counters", room_id=home.kitchen.id,
            estimated_minutes=10, last_done_at=KITCHEN_WEEK - timedelta(days=14),
        )
        add_task(
            name="Deep-clean the oven", room_id=home.kitchen.id, task_type="zone",
            estimated_minutes=45,
        )
        session = compose_session(
            db, for_user_id=owner.id, minutes=20, now=KITCHEN_WEEK
        )
        assert session == [r1, r2]

    def test_zone_scope_composes_the_zones_rooms_plus_its_missions(
        self, db, add_task, owner, home, zones_on
    ):
        dishes = add_task(name="Do the dishes", room_id=home.kitchen.id,
                          estimated_minutes=10)
        add_task(name="Make the bed", room_id=home.bedroom.id, estimated_minutes=10)
        microwave = add_task(
            name="Clean the microwave", room_id=home.kitchen.id, task_type="zone",
            estimated_minutes=10,
        )
        session = compose_session(
            db,
            for_user_id=owner.id,
            minutes=30,
            zone_id=home.kitchen_zone.id,
            now=KITCHEN_WEEK,
        )
        assert set(session) == {dishes, microwave}

    def test_zone_scope_outside_the_window_is_recurring_only(
        self, db, add_task, owner, home, zones_on
    ):
        # Picking Kitchen during Bedroom week: its rooms' recurring work,
        # while its missions wait for their week (the planning path — a
        # zone_mission_session with an explicit zone_id — is the way to
        # work them early). No stray door to old behavior.
        dishes = add_task(name="Do the dishes", room_id=home.kitchen.id,
                          estimated_minutes=10)
        add_task(
            name="Clean the microwave", room_id=home.kitchen.id, task_type="zone",
            estimated_minutes=10,
        )
        session = compose_session(
            db,
            for_user_id=owner.id,
            minutes=30,
            zone_id=home.kitchen_zone.id,
            now=BEDROOM_WEEK,
        )
        assert session == [dishes]

    def test_room_scope_takes_only_that_rooms_mission(
        self, db, add_task, owner, home, zones_on
    ):
        counters = add_task(
            name="Wipe down the counters", room_id=home.kitchen.id, estimated_minutes=10
        )
        microwave = add_task(
            name="Clean the microwave", room_id=home.kitchen.id, task_type="zone",
            estimated_minutes=10,
        )
        session = compose_session(
            db, for_user_id=owner.id, minutes=30, room_id=home.kitchen.id,
            now=KITCHEN_WEEK,
        )
        assert set(session) == {counters, microwave}


# ---------------------------------------------------------------------------
# Zone sessions — missions only, never dishes
# ---------------------------------------------------------------------------

class TestZoneMissionSession:
    def test_contains_only_missions_never_dishes(
        self, db, add_task, owner, home, zones_on
    ):
        # THE bug this whole effort exists to fix: dishes are the
        # dirtiest thing in the kitchen, and they still don't belong in a
        # Kitchen Zone session.
        add_task(
            name="Do the dishes", room_id=home.kitchen.id,
            last_done_at=KITCHEN_WEEK - timedelta(days=28),  # filthiest
        )
        shelf = add_task(
            name="Clean one refrigerator shelf", room_id=home.kitchen.id,
            task_type="zone", estimated_minutes=10,
        )
        microwave = add_task(
            name="Clean the microwave", room_id=home.kitchen.id, task_type="zone",
            estimated_minutes=10,
            last_done_at=KITCHEN_WEEK - timedelta(days=21),
        )
        session = zone_mission_session(
            db, for_user_id=owner.id, minutes=30, now=KITCHEN_WEEK
        )
        assert set(session) == {shelf, microwave}
        assert all(t.task_type == "zone" for t in session)

    def test_empty_pool_is_simply_empty(self, db, add_task, owner, home, zones_on):
        add_task(name="Do the dishes", room_id=home.kitchen.id)
        assert (
            zone_mission_session(db, for_user_id=owner.id, minutes=30, now=KITCHEN_WEEK)
            == []
        )

    def test_explicit_zone_id_is_the_planning_path(
        self, db, add_task, owner, home, zones_on
    ):
        # Working an inactive zone's missions on purpose still works —
        # from the Zones page, not the home screen.
        oven = add_task(
            name="Deep-clean the oven", room_id=home.kitchen.id, task_type="zone"
        )
        session = zone_mission_session(
            db, for_user_id=owner.id, zone_id=home.kitchen_zone.id, now=BEDROOM_WEEK
        )
        assert session == [oven]


# ---------------------------------------------------------------------------
# Guest mode — routines only, one clause
# ---------------------------------------------------------------------------

class TestGuestMode:
    def test_guest_mode_never_yields_a_zone_or_project_task(
        self, db, add_task, owner, home, zones_on
    ):
        tidy = add_task(
            name="Quick tidy", room_id=home.kitchen.id,
            guest_facing=True, effort="quick",
        )
        add_task(
            name="Wipe cabinet fronts", room_id=home.kitchen.id, task_type="zone",
            guest_facing=True, effort="quick",
        )
        add_task(
            name="Reorganize the closet", room_id=home.kitchen.id,
            task_type="project", guest_facing=True, effort="quick",
        )
        punch_list = candidate_tasks(db, guest_only=True, now=KITCHEN_WEEK)
        assert punch_list == [tidy]
        session = build_session(db, guest_only=True, minutes=30, now=KITCHEN_WEEK)
        assert session == [tidy]


# ---------------------------------------------------------------------------
# The gate — lanes only when flag AND overlay agree; legacy untouched
# ---------------------------------------------------------------------------

class TestLaneGate:
    def test_lanes_need_both_the_flag_and_the_overlay(self, db, owner):
        assert settings_service.lanes_active(db, owner.id) is False
        settings_service.set_settings(db, owner.id, {"zone_lane_enabled": "true"})
        assert settings_service.lanes_active(db, owner.id) is False  # zones still off
        settings_service.set_settings(db, owner.id, {"zones_enabled": "true"})
        assert settings_service.lanes_active(db, owner.id) is True
        settings_service.set_settings(db, owner.id, {"zone_lane_enabled": "false"})
        assert settings_service.lanes_active(db, owner.id) is False  # clean rollback

    def test_flag_off_legacy_focus_is_byte_identical(
        self, db, add_task, owner, home, zones_on
    ):
        # Flag off: daily_focus still serves the out-of-window mission
        # globally at full decay priority — yesterday's app, exactly.
        mission = add_task(
            name="Deep-clean the oven", room_id=home.kitchen.id, task_type="zone",
            last_done_at=BEDROOM_WEEK - timedelta(days=21),  # 3.0
        )
        routine = add_task(
            name="Do the dishes", room_id=home.kitchen.id,
            last_done_at=BEDROOM_WEEK - timedelta(days=14),  # 2.0
        )
        assert daily_focus(db, limit=3, now=BEDROOM_WEEK) == [mission, routine]


# ---------------------------------------------------------------------------
# Zone 3's rotating second room — one settings key, not a subsystem
# ---------------------------------------------------------------------------

class TestZone3ExtraRoom:
    def test_extra_rooms_missions_join_zone_3s_pool_when_set(
        self, db, add_task, owner, home, zones_on
    ):
        sink = add_task(
            name="Scrub the sink", room_id=home.bathroom.id, task_type="zone"
        )
        craft_bin = add_task(
            name="Sort one craft bin", room_id=home.craft.id, task_type="zone"
        )
        settings_service.set_settings(
            db, owner.id, {"zone_3_extra_room_id": str(home.craft.id)}
        )
        pool = zone_candidates(db, for_user_id=owner.id, now=BATHROOM_WEEK)
        assert set(pool) == {sink, craft_bin}

    def test_without_the_setting_they_dont(self, db, add_task, owner, home, zones_on):
        sink = add_task(
            name="Scrub the sink", room_id=home.bathroom.id, task_type="zone"
        )
        craft_bin = add_task(
            name="Sort one craft bin", room_id=home.craft.id, task_type="zone"
        )
        pool = zone_candidates(db, for_user_id=owner.id, now=BATHROOM_WEEK)
        assert sink in pool and craft_bin not in pool

    def test_the_union_is_zone_3_only(self, db, add_task, owner, home, zones_on):
        # During Kitchen week the extra room's missions stay out — the
        # setting belongs to Zone 3's week alone.
        craft_bin = add_task(
            name="Sort one craft bin", room_id=home.craft.id, task_type="zone"
        )
        settings_service.set_settings(
            db, owner.id, {"zone_3_extra_room_id": str(home.craft.id)}
        )
        assert craft_bin not in zone_candidates(
            db, for_user_id=owner.id, now=KITCHEN_WEEK
        )


# ---------------------------------------------------------------------------
# The waiting state — presentation only, never red debt
# ---------------------------------------------------------------------------

class TestWaitingState:
    def test_context_is_none_while_the_lanes_are_off(self, db, owner, home, zones_on):
        assert presentation_context(db, owner.id, now=KITCHEN_WEEK) is None

    def test_out_of_window_mission_reports_waiting_through_the_api(
        self, db, add_task, owner, home, zones_on, lane_on
    ):
        oven = add_task(
            name="Deep-clean the oven", room_id=home.kitchen.id, task_type="zone",
            last_done_at=BEDROOM_WEEK - timedelta(days=21),  # ratio 3.0 — "overdue"
        )
        ctx = presentation_context(db, owner.id, now=BEDROOM_WEEK)
        read = task_to_read(oven, now=BEDROOM_WEEK, ctx=ctx)
        assert read.band == "waiting"
        assert read.zone_name == "Kitchen"
        assert read.ratio == 3.0  # the ratio stays honest — only display changes

    def test_in_window_mission_shows_its_real_band(
        self, db, add_task, owner, home, zones_on, lane_on
    ):
        oven = add_task(
            name="Deep-clean the oven", room_id=home.kitchen.id, task_type="zone",
            last_done_at=KITCHEN_WEEK - timedelta(days=21),
        )
        ctx = presentation_context(db, owner.id, now=KITCHEN_WEEK)
        read = task_to_read(oven, now=KITCHEN_WEEK, ctx=ctx)
        assert read.band == band_for_ratio(3.0) == "overdue"
        assert read.zone_name == "Kitchen"

    def test_routines_never_wait(self, db, add_task, owner, home, zones_on, lane_on):
        dishes = add_task(name="Do the dishes", room_id=home.kitchen.id)
        ctx = presentation_context(db, owner.id, now=BEDROOM_WEEK)
        assert in_zone_window(dishes, ctx) is True
        assert task_to_read(dishes, now=BEDROOM_WEEK, ctx=ctx).band != "waiting"

    def test_room_aggregate_ignores_out_of_window_missions(
        self, db, add_task, owner, home, zones_on, lane_on
    ):
        fresh_routine = add_task(
            name="Do the dishes", room_id=home.kitchen.id,
            last_done_at=BEDROOM_WEEK - timedelta(days=1),  # ratio ~0.14
        )
        neglected_mission = add_task(
            name="Deep-clean the oven", room_id=home.kitchen.id, task_type="zone",
            last_done_at=BEDROOM_WEEK - timedelta(days=21),  # ratio 3.0
        )
        tasks = [fresh_routine, neglected_mission]
        ctx = presentation_context(db, owner.id, now=BEDROOM_WEEK)
        with_ctx = room_aggregate_ratio(tasks, now=BEDROOM_WEEK, ctx=ctx)
        without_ctx = room_aggregate_ratio(tasks, now=BEDROOM_WEEK)
        # The room reads from its askable work only — the waiting mission
        # can't turn the kitchen red during Bedroom week.
        assert with_ctx == dirtiness_ratio(fresh_routine, BEDROOM_WEEK)
        assert without_ctx > with_ctx

    def test_extra_room_mission_is_in_window_during_zone_3s_week(
        self, db, add_task, owner, home, zones_on, lane_on
    ):
        craft_bin = add_task(
            name="Sort one craft bin", room_id=home.craft.id, task_type="zone"
        )
        settings_service.set_settings(
            db, owner.id, {"zone_3_extra_room_id": str(home.craft.id)}
        )
        during = presentation_context(db, owner.id, now=BATHROOM_WEEK)
        assert in_zone_window(craft_bin, during) is True
        assert window_zone_name(craft_bin, during) == "Bathroom"
        outside = presentation_context(db, owner.id, now=KITCHEN_WEEK)
        assert in_zone_window(craft_bin, outside) is False


# ---------------------------------------------------------------------------
# Issue #37/#14 — the home screen and the nudge never un-rest a task
# ---------------------------------------------------------------------------

class TestComposedFocusNeverShowsResting:
    def test_compose_focus_is_empty_when_everything_eligible_is_resting(
        self, db, add_task, owner, home, zones_on, lane_on
    ):
        # A rested routine and a rested current-zone mission: the home
        # celebrates instead of resurfacing either (issue #37) — unlike
        # sessions, where the issue-#8 fallback still applies.
        add_task(
            name="Do the dishes", room_id=home.kitchen.id,
            snoozed_until=KITCHEN_WEEK + timedelta(hours=3),
        )
        add_task(
            name="Clean the microwave", room_id=home.kitchen.id, task_type="zone",
            snoozed_until=KITCHEN_WEEK + timedelta(hours=3),
        )
        assert compose_focus(db, limit=3, for_user_id=owner.id, now=KITCHEN_WEEK) == []

    def test_a_rested_mission_never_takes_the_mission_slot(
        self, db, add_task, owner, home, zones_on, lane_on
    ):
        routine = add_task(name="Do the dishes", room_id=home.kitchen.id)
        add_task(
            name="Clean the microwave", room_id=home.kitchen.id, task_type="zone",
            snoozed_until=KITCHEN_WEEK + timedelta(hours=3),
        )
        cards = compose_focus(db, limit=3, for_user_id=owner.id, now=KITCHEN_WEEK)
        assert cards == [routine]


class TestDailyNudgeMirrorsHome:
    """Issue #14: the push must be composed by the same path as the home
    screen — composer when the lanes are active, legacy otherwise — and
    must never name a resting task on either path (issue #37)."""

    def test_nudge_routes_through_the_composer_when_lanes_are_active(
        self, db, add_task, owner, home, zones_on, lane_on, monkeypatch
    ):
        from app.services import reminder_service, scheduling

        seen = {}

        def fake_compose_focus(db_, *, limit, for_user_id, effort=None, now=None, tz=None):
            seen["called"] = True
            return []

        monkeypatch.setattr(scheduling, "compose_focus", fake_compose_focus)
        title, body = reminder_service.compose_daily_nudge(db, owner)
        assert seen.get("called") is True
        assert "good shape" in body

    def test_nudge_never_names_a_resting_task_on_the_legacy_path(
        self, db, add_task, owner, monkeypatch
    ):
        from app.services import reminder_service

        # Overdue but freshly rested (relative to the real clock the
        # nudge composes with): the push says "in good shape", it does
        # not name the task she asked to rest.
        real_now = datetime.now(timezone.utc)
        add_task(
            name="Scrub the tub",
            last_done_at=real_now - timedelta(days=14),
            snoozed_until=real_now + timedelta(hours=3),
        )
        title, body = reminder_service.compose_daily_nudge(db, owner)
        assert "Scrub the tub" not in body
        assert "good shape" in body
