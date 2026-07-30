"""Tests for the zone calendar (SPEC §6, Phase 10) — the first coverage
week_of_month and current_zone have ever had (Phase 7 covered decay
only). Weeks run Monday–Sunday: a partial week at the start of the month
is week 1 (FlyLady's "the first few days of the month"), and anything
past the fourth week clamps to 5, so zones 1 and 5 often share a
calendar week.

The month-shape math: with `fw` = the weekday of the 1st (Monday = 0),
week 1 holds days 1..(7 - fw) and week 2 begins on day (8 - fw) — the
first Monday after day 1 (day 8 when the month itself starts Monday).
"""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.models import Zone
from app.services.zones import current_zone, week_of_month, zone_for_moment

NEW_YORK = ZoneInfo("America/New_York")


@pytest.fixture()
def five_zones(db):
    """The five FlyLady zone lanes, one per week-of-month."""
    zones = [
        Zone(name=f"Zone {week}", week_of_month=week, sort_order=week)
        for week in range(1, 6)
    ]
    db.add_all(zones)
    db.flush()
    return {zone.week_of_month: zone for zone in zones}


class TestWeekOfMonth:
    # One 2026 month for each weekday a month can begin on.
    MONTHS = [
        (2026, 6, 0),   # June starts Monday
        (2026, 9, 1),   # September starts Tuesday
        (2026, 4, 2),   # April starts Wednesday
        (2026, 1, 3),   # January starts Thursday
        (2026, 5, 4),   # May starts Friday
        (2026, 8, 5),   # August starts Saturday
        (2026, 2, 6),   # February starts Sunday
    ]

    @pytest.mark.parametrize("year,month,fw", MONTHS)
    def test_months_beginning_on_every_weekday(self, year, month, fw):
        assert date(year, month, 1).weekday() == fw  # the premise
        # The opening partial (or full) week is always week 1.
        assert week_of_month(date(year, month, 1)) == 1
        week2 = 8 - fw  # the first Monday after day 1
        assert date(year, month, week2).weekday() == 0
        assert week_of_month(date(year, month, week2 - 1)) == 1
        assert week_of_month(date(year, month, week2)) == 2
        # Each subsequent Monday advances the week.
        assert week_of_month(date(year, month, week2 + 7)) == 3
        assert week_of_month(date(year, month, week2 + 14)) == 4
        assert week_of_month(date(year, month, week2 + 21)) == 5

    def test_february_at_28_days(self):
        # Feb 2026 starts on a Sunday, so week 1 is that single day and
        # the 28th still lands in (clamped) week 5.
        assert week_of_month(date(2026, 2, 1)) == 1
        assert week_of_month(date(2026, 2, 2)) == 2  # the first Monday
        assert week_of_month(date(2026, 2, 28)) == 5

    def test_leap_year_february(self):
        # Feb 2028 starts on a Tuesday and has 29 days.
        assert date(2028, 2, 1).weekday() == 1
        assert week_of_month(date(2028, 2, 1)) == 1
        assert week_of_month(date(2028, 2, 7)) == 2
        assert week_of_month(date(2028, 2, 29)) == 5

    def test_thirty_day_month_ends_in_week_five(self):
        # June 2026 starts on a Monday: four exact weeks then days 29–30.
        assert week_of_month(date(2026, 6, 28)) == 4
        assert week_of_month(date(2026, 6, 29)) == 5
        assert week_of_month(date(2026, 6, 30)) == 5

    def test_thirty_one_day_month_clamps_to_week_five(self):
        # Aug 2026 starts on a Saturday; the raw arithmetic would call
        # the 31st "week 6" — it must clamp so the month's last days
        # always belong to zone 5.
        assert week_of_month(date(2026, 8, 24)) == 5
        assert week_of_month(date(2026, 8, 31)) == 5


class TestCurrentZone:
    def test_zone_five_to_next_months_zone_one_boundary(self, db, five_zones):
        # July 31 2026 is week 5; August 1 is week 1 — the rollover is
        # nothing but a different answer from this lookup (the no-debt
        # rule rides on that).
        assert current_zone(db, date(2026, 7, 31)) is five_zones[5]
        assert current_zone(db, date(2026, 8, 1)) is five_zones[1]

    def test_no_zones_seeded_means_none(self, db):
        assert current_zone(db, date(2026, 7, 15)) is None


class TestZoneForMoment:
    """The zone must flip on HER midnight, not UTC's. At 03:00 UTC on
    Aug 1 2026 it is still 23:00 July 31 in New York (EDT, UTC-4)."""

    def test_still_the_old_zone_just_before_her_midnight(self, db, five_zones):
        now = datetime(2026, 8, 1, 3, 0, 0, tzinfo=timezone.utc)
        assert zone_for_moment(db, now, NEW_YORK) is five_zones[5]

    def test_the_new_zone_just_after_her_midnight(self, db, five_zones):
        now = datetime(2026, 8, 1, 4, 1, 0, tzinfo=timezone.utc)  # 00:01 EDT
        assert zone_for_moment(db, now, NEW_YORK) is five_zones[1]

    def test_a_utc_household_flips_on_utc_midnight(self, db, five_zones):
        now = datetime(2026, 8, 1, 0, 1, 0, tzinfo=timezone.utc)
        assert zone_for_moment(db, now, timezone.utc) is five_zones[1]
