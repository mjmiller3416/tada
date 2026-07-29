"""Unit tests for the pure decay-engine functions (SPEC §4).

These tests document CURRENT behavior against SPEC §4. The engine runs
in production and a July 2026 review found it matches the spec exactly —
if one of these fails after an engine change, suspect the change, not
the test. No database needed: plain Task objects and an explicit `now`.

Timestamps are chosen so the ratio math is exact in floating point
(e.g. 3.5 days on a 7-day cadence is exactly 0.5), which lets the band
boundaries be tested with == instead of approx.
"""

from datetime import datetime, timedelta, timezone

import pytest

from zoneinfo import ZoneInfo

from app.services.scheduling import (
    BAND_AGING,
    BAND_DUE,
    BAND_OVERDUE,
    DAILY_BOOST,
    NEVER_DONE_RATIO,
    PREFERRED_DAY_BOOST,
    SNOOZE_OFFSETS,
    band_for_ratio,
    dirtiness_ratio,
    is_snoozed,
    preferred_day_boost,
    priority_score,
    rank_tasks,
    room_aggregate_ratio,
    snooze_task,
)

NOW = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)


def days_ago(days: float) -> datetime:
    return NOW - timedelta(days=days)


# ---------------------------------------------------------------------------
# 1. dirtiness_ratio
# ---------------------------------------------------------------------------

class TestDirtinessRatio:
    def test_zero_elapsed_is_zero(self, make_task):
        task = make_task(cadence_days=7, last_done_at=NOW)
        assert dirtiness_ratio(task, NOW) == 0.0

    def test_exactly_one_cadence_is_one(self, make_task):
        task = make_task(cadence_days=7, last_done_at=days_ago(7))
        assert dirtiness_ratio(task, NOW) == 1.0

    def test_fractional_cadence(self, make_task):
        task = make_task(cadence_days=7, last_done_at=days_ago(3.5))
        assert dirtiness_ratio(task, NOW) == 0.5
        task = make_task(cadence_days=7, last_done_at=days_ago(10.5))
        assert dirtiness_ratio(task, NOW) == 1.5

    def test_well_past_cadence(self, make_task):
        task = make_task(cadence_days=7, last_done_at=days_ago(21))
        assert dirtiness_ratio(task, NOW) == 3.0

    def test_never_done_reads_as_never_done_ratio(self, make_task):
        task = make_task(cadence_days=7, last_done_at=None)
        assert dirtiness_ratio(task, NOW) == NEVER_DONE_RATIO

    def test_daily_cadence_extreme(self, make_task):
        # cadence_days=1 is her real minimum (daily tasks)
        assert dirtiness_ratio(make_task(cadence_days=1, last_done_at=days_ago(0.5)), NOW) == 0.5
        assert dirtiness_ratio(make_task(cadence_days=1, last_done_at=days_ago(1)), NOW) == 1.0
        assert dirtiness_ratio(make_task(cadence_days=1, last_done_at=days_ago(1.5)), NOW) == 1.5

    def test_annual_cadence_extreme(self, make_task):
        # cadence_days=365 is her real maximum (annual tasks)
        assert dirtiness_ratio(make_task(cadence_days=365, last_done_at=days_ago(182.5)), NOW) == 0.5
        assert dirtiness_ratio(make_task(cadence_days=365, last_done_at=days_ago(365)), NOW) == 1.0

    def test_future_last_done_clamps_to_zero(self, make_task):
        # The engine clamps rather than going negative; the UI (Phase 4.6)
        # separately refuses to store a future date.
        task = make_task(cadence_days=7, last_done_at=NOW + timedelta(days=2))
        assert dirtiness_ratio(task, NOW) == 0.0

    def test_naive_datetime_is_treated_as_utc(self, make_task):
        # SQLite returns naive datetimes; _aware() must normalize them.
        naive = days_ago(7).replace(tzinfo=None)
        task = make_task(cadence_days=7, last_done_at=naive)
        assert dirtiness_ratio(task, NOW) == 1.0


# ---------------------------------------------------------------------------
# 2. Band boundaries — exactly ON each threshold and just either side
# ---------------------------------------------------------------------------

class TestBands:
    def test_thresholds_match_spec(self):
        # SPEC §4 fixes these numbers; the UI's every color and copy string
        # keys off them.
        assert BAND_AGING == 0.5
        assert BAND_DUE == 0.9
        assert BAND_OVERDUE == 1.2

    @pytest.mark.parametrize(
        ("ratio", "band"),
        [
            (0.0, "fresh"),
            (0.4999, "fresh"),   # just under the aging threshold
            (0.5, "aging"),      # exactly on: 0.5 <= ratio < 0.9 is aging
            (0.5001, "aging"),
            (0.8999, "aging"),   # just under the due threshold
            (0.9, "due"),        # exactly on: 0.9 <= ratio < 1.2 is due
            (0.9001, "due"),
            (1.1999, "due"),     # just under the overdue threshold
            (1.2, "overdue"),    # exactly on: ratio >= 1.2 is overdue
            (1.2001, "overdue"),
            (5.0, "overdue"),
        ],
    )
    def test_band_edges(self, ratio, band):
        assert band_for_ratio(ratio) == band

    def test_never_done_lands_in_overdue(self):
        assert band_for_ratio(NEVER_DONE_RATIO) == "overdue"


# ---------------------------------------------------------------------------
# 3. rank_tasks — priority order, tie-breaks, stability, the daily boost
# ---------------------------------------------------------------------------

class TestRankTasks:
    def test_orders_by_ratio_descending(self, make_task):
        aging = make_task(name="aging", cadence_days=7, last_done_at=days_ago(4.2))    # 0.6
        overdue = make_task(name="overdue", cadence_days=7, last_done_at=days_ago(14))  # 2.0
        due = make_task(name="due", cadence_days=7, last_done_at=days_ago(7))           # 1.0
        assert rank_tasks([aging, overdue, due], NOW) == [overdue, due, aging]

    def test_daily_boost_lifts_an_undone_daily_over_a_dirtier_weekly(self, make_task):
        # SPEC §4: dailies must reliably surface each day. Ratio 1.2 + 0.5
        # boost = 1.7 beats the weekly's raw 1.6.
        daily = make_task(name="daily", cadence_days=1, last_done_at=days_ago(1.2))
        weekly = make_task(name="weekly", cadence_days=7, last_done_at=days_ago(11.2))  # 1.6
        assert priority_score(daily, NOW) == pytest.approx(1.2 + DAILY_BOOST)
        assert rank_tasks([daily, weekly], NOW) == [daily, weekly]

    def test_daily_done_today_gets_no_boost(self, make_task):
        # Boost only applies at ratio >= 1.0 — a daily done this morning
        # doesn't jump the queue.
        daily = make_task(name="daily", cadence_days=1, last_done_at=days_ago(0.6))
        weekly = make_task(name="weekly", cadence_days=7, last_done_at=days_ago(5.6))  # 0.8
        assert priority_score(daily, NOW) == 0.6
        assert rank_tasks([daily, weekly], NOW) == [weekly, daily]

    def test_score_tie_broken_by_raw_ratio_puts_overdue_before_due(self, make_task):
        # A boosted daily at raw 1.0 (band "due") ties on score 1.5 with a
        # weekly at raw 1.5 (band "overdue"). SPEC §4's "overdue before
        # due, then higher ratio" tie-break resolves it: the overdue task
        # leads.
        daily = make_task(name="daily", cadence_days=1, last_done_at=days_ago(1))       # 1.0 + 0.5
        weekly = make_task(name="weekly", cadence_days=7, last_done_at=days_ago(10.5))  # 1.5
        assert priority_score(daily, NOW) == priority_score(weekly, NOW)
        assert rank_tasks([daily, weekly], NOW) == [weekly, daily]

    def test_equal_ratio_tie_broken_by_longer_since_last_done(self, make_task):
        # Same ratio 2.0, but one was last touched twice as long ago.
        recent = make_task(name="recent", cadence_days=2, last_done_at=days_ago(4))
        ancient = make_task(name="ancient", cadence_days=4, last_done_at=days_ago(8))
        assert dirtiness_ratio(recent, NOW) == dirtiness_ratio(ancient, NOW) == 2.0
        assert rank_tasks([recent, ancient], NOW) == [ancient, recent]

    def test_genuinely_identical_tasks_keep_input_order(self, make_task):
        # sorted() is stable; two indistinguishable tasks never swap.
        first = make_task(name="first", cadence_days=7, last_done_at=days_ago(14))
        second = make_task(name="second", cadence_days=7, last_done_at=days_ago(14))
        assert rank_tasks([first, second], NOW) == [first, second]
        assert rank_tasks([second, first], NOW) == [second, first]


# ---------------------------------------------------------------------------
# 4. Never-done handling in the ranking
# ---------------------------------------------------------------------------

class TestNeverDone:
    def test_never_done_sorts_between_dirtier_and_cleaner_tasks(self, make_task):
        # NEVER_DONE_RATIO = 1.5: high priority (overdue band) but not
        # drowning genuinely ancient tasks (SPEC §4).
        never = make_task(name="never", cadence_days=7, last_done_at=None)
        ancient = make_task(name="ancient", cadence_days=7, last_done_at=days_ago(11.9))  # 1.7
        due = make_task(name="due", cadence_days=7, last_done_at=days_ago(7))             # 1.0
        assert rank_tasks([due, never, ancient], NOW) == [ancient, never, due]

    def test_never_done_wins_tie_against_equal_ratio(self, make_task):
        # At an identical score and ratio, "never" counts as longest since
        # last done and leads.
        never = make_task(name="never", cadence_days=7, last_done_at=None)
        done_once = make_task(name="done-once", cadence_days=7, last_done_at=days_ago(10.5))  # 1.5
        assert dirtiness_ratio(done_once, NOW) == NEVER_DONE_RATIO
        assert rank_tasks([done_once, never], NOW) == [never, done_once]

    def test_never_done_daily_gets_the_daily_boost(self, make_task):
        # Documents current behavior: a never-done daily reads 1.5 >= 1.0,
        # so the boost applies on top.
        never_daily = make_task(cadence_days=1, last_done_at=None)
        assert priority_score(never_daily, NOW) == NEVER_DONE_RATIO + DAILY_BOOST


# ---------------------------------------------------------------------------
# 5. room_aggregate_ratio — the max/average blend
# ---------------------------------------------------------------------------

class TestRoomAggregateRatio:
    def test_blend_is_half_max_half_average(self, make_task):
        tasks = [
            make_task(cadence_days=10, last_done_at=days_ago(13)),  # 1.3
            make_task(cadence_days=10, last_done_at=days_ago(5)),   # 0.5
            make_task(cadence_days=10, last_done_at=days_ago(3)),   # 0.3
        ]
        expected = 0.5 * 1.3 + 0.5 * ((1.3 + 0.5 + 0.3) / 3)
        assert room_aggregate_ratio(tasks, NOW) == pytest.approx(expected)

    def test_one_filthy_task_colors_the_room_without_drowning_nine_greens(self, make_task):
        # One red (1.3) among nine fresh greens (0.1): the room reads
        # "aging" — visibly colored, but a single red never paints the
        # whole room red (SPEC §4).
        red = make_task(cadence_days=10, last_done_at=days_ago(13))
        greens = [make_task(cadence_days=10, last_done_at=days_ago(1)) for _ in range(9)]
        result = room_aggregate_ratio([red] + greens, NOW)
        assert result == pytest.approx(0.5 * 1.3 + 0.5 * ((1.3 + 9 * 0.1) / 10))
        assert band_for_ratio(result) == "aging"

    def test_single_task_room_reads_as_that_task(self, make_task):
        task = make_task(cadence_days=10, last_done_at=days_ago(7))  # 0.7
        assert room_aggregate_ratio([task], NOW) == pytest.approx(0.7)

    def test_inactive_tasks_are_ignored(self, make_task):
        active = make_task(cadence_days=10, last_done_at=days_ago(1), is_active=True)    # 0.1
        retired = make_task(cadence_days=10, last_done_at=days_ago(50), is_active=False)  # 5.0
        assert room_aggregate_ratio([active, retired], NOW) == pytest.approx(0.1)

    def test_empty_room_returns_none(self, make_task):
        assert room_aggregate_ratio([], NOW) is None
        only_inactive = [make_task(cadence_days=10, last_done_at=days_ago(1), is_active=False)]
        assert room_aggregate_ratio(only_inactive, NOW) is None


# ---------------------------------------------------------------------------
# 6. is_snoozed / snooze_task — defer the reminder, never the decay
# ---------------------------------------------------------------------------

class TestSnooze:
    def test_before_expiry_is_snoozed(self, make_task):
        task = make_task(snoozed_until=NOW + timedelta(hours=1))
        assert is_snoozed(task, NOW) is True

    def test_exactly_at_expiry_is_not_snoozed(self, make_task):
        # Strict '>': the moment the clock reaches snoozed_until, the task
        # is back.
        task = make_task(snoozed_until=NOW)
        assert is_snoozed(task, NOW) is False

    def test_after_expiry_is_not_snoozed(self, make_task):
        task = make_task(snoozed_until=NOW - timedelta(hours=1))
        assert is_snoozed(task, NOW) is False

    def test_never_snoozed_is_not_snoozed(self, make_task):
        assert is_snoozed(make_task(snoozed_until=None), NOW) is False

    @pytest.mark.parametrize("option", ["later_today", "tomorrow", "few_days"])
    def test_snooze_sets_the_fixed_offset(self, make_task, option):
        task = make_task()
        result = snooze_task(task, option, NOW)
        assert task.snoozed_until == NOW + SNOOZE_OFFSETS[option]
        assert result == task.snoozed_until
        assert is_snoozed(task, NOW) is True

    def test_wake_clears_an_active_snooze(self, make_task):
        task = make_task(snoozed_until=NOW + timedelta(days=3))
        result = snooze_task(task, "wake", NOW)
        assert task.snoozed_until is None
        assert result == NOW

    def test_snooze_never_touches_last_done_or_the_ratio(self, make_task):
        # The decay-aware snooze (SPEC §6): the task keeps aging quietly.
        last_done = days_ago(5)
        task = make_task(cadence_days=7, last_done_at=last_done)
        ratio_before = dirtiness_ratio(task, NOW)
        snooze_task(task, "few_days", NOW)
        assert task.last_done_at == last_done
        assert dirtiness_ratio(task, NOW) == ratio_before


# ---------------------------------------------------------------------------
# Preferred-day boost (Phase 8) — a BOOST, never a schedule
# ---------------------------------------------------------------------------

# Her scenario verbatim: laundry is a Saturday thing. Python weekday()
# convention throughout (Monday = 0 ... Sunday = 6).
SATURDAY = 5
SUNDAY = 6
SAT_NOON = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)   # a Saturday
SUN_NOON = SAT_NOON + timedelta(days=1)                          # the grace day
MON_NOON = SAT_NOON + timedelta(days=2)                          # quiet again
WED_NOON = SAT_NOON + timedelta(days=4)                          # an ordinary day


def test_weekday_fixture_sanity():
    assert SAT_NOON.weekday() == SATURDAY
    assert SUN_NOON.weekday() == SUNDAY


class TestPreferredDayBoost:
    def laundry(self, make_task, last_done: datetime):
        return make_task(
            name="laundry", cadence_days=7, preferred_day=SATURDAY, last_done_at=last_done
        )

    def test_boosted_on_the_preferred_day(self, make_task):
        # Done last Saturday -> ratio 1.0 today. Boosted, it leads over a
        # never-done task (1.5) and a genuinely overdue weekly (2.0) —
        # "laundry leads on Saturday in normal conditions".
        laundry = self.laundry(make_task, SAT_NOON - timedelta(days=7))
        never = make_task(name="never", cadence_days=7, last_done_at=None)
        overdue = make_task(
            name="overdue", cadence_days=7, last_done_at=SAT_NOON - timedelta(days=14)
        )
        assert preferred_day_boost(laundry, SAT_NOON) == PREFERRED_DAY_BOOST
        assert priority_score(laundry, SAT_NOON) == pytest.approx(1.0 + PREFERRED_DAY_BOOST)
        assert rank_tasks([never, overdue, laundry], SAT_NOON) == [laundry, overdue, never]

    def test_boosted_on_the_grace_day(self, make_task):
        # It didn't happen Saturday: still boosted Sunday.
        laundry = self.laundry(make_task, SAT_NOON - timedelta(days=7))
        assert preferred_day_boost(laundry, SUN_NOON) == PREFERRED_DAY_BOOST
        assert priority_score(laundry, SUN_NOON) == pytest.approx(
            8 / 7 + PREFERRED_DAY_BOOST
        )

    def test_quiet_after_the_grace_day(self, make_task):
        # Monday: no boost, no penalty, no different state — the task just
        # keeps decaying like any other until next Saturday.
        laundry = self.laundry(make_task, SAT_NOON - timedelta(days=7))
        assert preferred_day_boost(laundry, MON_NOON) == 0.0
        assert priority_score(laundry, MON_NOON) == dirtiness_ratio(laundry, MON_NOON)

    def test_quiet_on_an_ordinary_day(self, make_task):
        # Midweek, a dirtier task outranks Saturday-tagged laundry as if
        # the preference didn't exist.
        laundry = self.laundry(make_task, WED_NOON - timedelta(days=7))       # 1.0
        dirtier = make_task(
            name="dirtier", cadence_days=7, last_done_at=WED_NOON - timedelta(days=8)
        )  # ~1.14
        assert preferred_day_boost(laundry, WED_NOON) == 0.0
        assert rank_tasks([laundry, dirtier], WED_NOON) == [dirtier, laundry]

    def test_no_preference_means_no_boost(self, make_task):
        plain = make_task(name="plain", cadence_days=7, last_done_at=days_ago(7))
        assert preferred_day_boost(plain, NOW) == 0.0

    def test_shared_preferred_day_keeps_decay_order(self, make_task):
        # Two Saturday jobs boost equally and order among themselves by
        # normal decay priority — additive boost, not a pin.
        towels = make_task(
            name="towels",
            cadence_days=7,
            preferred_day=SATURDAY,
            last_done_at=SAT_NOON - timedelta(days=10.5),  # 1.5
        )
        laundry = self.laundry(make_task, SAT_NOON - timedelta(days=7))  # 1.0
        assert preferred_day_boost(towels, SAT_NOON) == preferred_day_boost(
            laundry, SAT_NOON
        )
        assert rank_tasks([laundry, towels], SAT_NOON) == [towels, laundry]

    def test_neglected_task_still_edges_above_a_boosted_one(self, make_task):
        # NOT a pin: something truly neglected (3.5 cadences past due)
        # outranks boosted laundry at ratio 1.0 + 2.0 = 3.0.
        laundry = self.laundry(make_task, SAT_NOON - timedelta(days=7))
        neglected = make_task(
            name="neglected", cadence_days=7, last_done_at=SAT_NOON - timedelta(days=24.5)
        )  # 3.5
        assert rank_tasks([laundry, neglected], SAT_NOON) == [neglected, laundry]

    def test_fresh_task_never_boosts(self, make_task):
        # She did laundry Wednesday: by Saturday the ratio is 3/7 (fresh),
        # so Saturday simply stays quiet — the decay answers "does
        # Saturday still fire?" and the planning list stays honest.
        laundry = self.laundry(make_task, SAT_NOON - timedelta(days=3))
        assert dirtiness_ratio(laundry, SAT_NOON) < BAND_AGING
        assert preferred_day_boost(laundry, SAT_NOON) == 0.0
        assert priority_score(laundry, SAT_NOON) == dirtiness_ratio(laundry, SAT_NOON)

    def test_boost_gate_matches_the_aging_threshold(self, make_task):
        # Exactly at BAND_AGING (3.5 of 7 days = 0.5) the task is no
        # longer fresh, so the boost applies.
        laundry = self.laundry(make_task, SAT_NOON - timedelta(days=3.5))
        assert preferred_day_boost(laundry, SAT_NOON) == PREFERRED_DAY_BOOST

    def test_never_done_task_boosts_on_its_day(self, make_task):
        never = make_task(name="never", cadence_days=7, preferred_day=SATURDAY)
        assert priority_score(never, SAT_NOON) == NEVER_DONE_RATIO + PREFERRED_DAY_BOOST

    def test_sunday_grace_wraps_to_monday(self, make_task):
        # preferred_day=6 (Sunday) must grace into Monday, not weekday 7.
        sunday_job = make_task(
            name="sheets",
            cadence_days=7,
            preferred_day=SUNDAY,
            last_done_at=MON_NOON - timedelta(days=7),
        )
        assert preferred_day_boost(sunday_job, MON_NOON) == PREFERRED_DAY_BOOST
        assert preferred_day_boost(sunday_job, WED_NOON) == 0.0

    def test_today_means_her_local_day_not_utc(self, make_task):
        # Monday 02:00 UTC is still Sunday evening in New York — the grace
        # day. Without her timezone the boost would already have lapsed.
        late_sunday = datetime(2026, 7, 6, 2, 0, 0, tzinfo=timezone.utc)
        new_york = ZoneInfo("America/New_York")
        laundry = self.laundry(make_task, late_sunday - timedelta(days=7))
        assert preferred_day_boost(laundry, late_sunday, tz=new_york) == PREFERRED_DAY_BOOST
        assert preferred_day_boost(laundry, late_sunday) == 0.0

    def test_boost_never_touches_ratio_band_or_last_done(self, make_task):
        # Ranking only: dirtiness, its band, and the anchor are identical
        # on and off the preferred day — nothing ever becomes "overdue"
        # because of a day preference.
        last_done = SAT_NOON - timedelta(days=7)
        laundry = self.laundry(make_task, last_done)
        assert dirtiness_ratio(laundry, SAT_NOON) == 1.0
        assert band_for_ratio(dirtiness_ratio(laundry, SAT_NOON)) == "due"
        priority_score(laundry, SAT_NOON)
        assert laundry.last_done_at == last_done
        assert dirtiness_ratio(laundry, SAT_NOON) == 1.0
