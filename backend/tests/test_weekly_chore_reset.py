"""The weekly-chore Monday reset (SPEC §6 kid chores).

The one deliberate step off "decay, not a calendar" (SPEC §1): a
weekly-cadence chore (cadence_days == 7) on the kid chore surface resets on
a fixed Monday instead of rolling decay. It reappears every Monday in the
member's LOCAL week and drops out the moment it's done that week; every
other chore keeps the decay freshness gate. Only chores_for_user is
affected — the decay engine everywhere else is unchanged.

`now` and `tz` are passed explicitly so the Monday boundary is exact and
the tests don't depend on when they run.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.services.scheduling import chores_for_user

# 2026-08-17 is a Monday, so this week's local boundary is 2026-08-17 00:00.
MON = datetime(2026, 8, 17, 0, 0, tzinfo=timezone.utc)  # this week's Monday
WED = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)  # mid-week
SUN = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)  # end of this week
NEXT_MON = datetime(2026, 8, 24, 8, 0, tzinfo=timezone.utc)  # next week's Monday

EASTERN = ZoneInfo("America/New_York")  # UTC-4 in August


def at(y, m, d, h=12) -> datetime:
    return datetime(y, m, d, h, 0, tzinfo=timezone.utc)


@pytest.fixture()
def add_task(db, make_task):
    """Persist a Task so chores_for_user's query can see it."""

    def _add(**overrides):
        task = make_task(**overrides)
        db.add(task)
        db.flush()
        return task

    return _add


def names(tasks) -> set[str]:
    return {t.name for t in tasks}


class TestWeeklyChoreMondayReset:
    def test_done_this_week_is_hidden(self, db, kid, add_task):
        add_task(name="Take out trash", cadence_days=7, assignee_id=kid.id,
                 last_done_at=at(2026, 8, 18))  # Tuesday, this week
        mine, _ = chores_for_user(db, kid.id, now=WED, tz=timezone.utc)
        assert names(mine) == set()

    def test_done_last_week_reappears(self, db, kid, add_task):
        add_task(name="Take out trash", cadence_days=7, assignee_id=kid.id,
                 last_done_at=at(2026, 8, 16))  # Sunday, last week
        mine, _ = chores_for_user(db, kid.id, now=WED, tz=timezone.utc)
        assert names(mine) == {"Take out trash"}

    def test_never_done_shows(self, db, kid, add_task):
        add_task(name="Feed the fish", cadence_days=7, assignee_id=kid.id,
                 last_done_at=None)
        mine, _ = chores_for_user(db, kid.id, now=WED, tz=timezone.utc)
        assert names(mine) == {"Feed the fish"}

    def test_stays_done_until_next_monday_even_past_decay(self, db, kid, add_task):
        # Done Monday this week; by Sunday it's ~6 days old (ratio ~0.86),
        # so plain decay WOULD resurface it — the Monday reset holds it.
        task = add_task(name="Water plants", cadence_days=7, assignee_id=kid.id,
                        last_done_at=at(2026, 8, 17))
        mine, _ = chores_for_user(db, kid.id, now=SUN, tz=timezone.utc)
        assert names(mine) == set()
        # ...and the following Monday it returns, history intact.
        mine, _ = chores_for_user(db, kid.id, now=NEXT_MON, tz=timezone.utc)
        assert names(mine) == {"Water plants"}
        assert task.last_done_at == at(2026, 8, 17)  # gate reads it, never mutates

    def test_monday_reset_boundary(self, db, kid, add_task):
        add_task(name="Sunday chore", cadence_days=7, assignee_id=kid.id,
                 last_done_at=at(2026, 8, 16))  # last Sunday -> due Monday
        add_task(name="Monday chore", cadence_days=7, assignee_id=kid.id,
                 last_done_at=datetime(2026, 8, 17, 6, 0, tzinfo=timezone.utc))  # this Mon
        mine, _ = chores_for_user(db, kid.id, now=MON.replace(hour=8), tz=timezone.utc)
        assert names(mine) == {"Sunday chore"}


class TestNonWeeklyChoresUnaffected:
    def test_fresh_monthly_chore_stays_hidden(self, db, kid, add_task):
        # Cadence 30, done 3 days ago -> ratio 0.1, fresh. The weekly reset
        # must not apply: a non-weekly chore still follows plain decay.
        add_task(name="Wipe baseboards", cadence_days=30, assignee_id=kid.id,
                 last_done_at=at(2026, 8, 16))
        mine, _ = chores_for_user(db, kid.id, now=WED, tz=timezone.utc)
        assert names(mine) == set()

    def test_overdue_monthly_chore_shows(self, db, kid, add_task):
        add_task(name="Wipe baseboards", cadence_days=30, assignee_id=kid.id,
                 last_done_at=at(2026, 6, 1))  # ~79 days -> ratio ~2.6
        mine, _ = chores_for_user(db, kid.id, now=WED, tz=timezone.utc)
        assert names(mine) == {"Wipe baseboards"}


class TestUpForGrabs:
    def test_claimable_weekly_resets_monday(self, db, kid, add_task):
        add_task(name="Sweep porch", cadence_days=7, assignee_id=None, claimable=True,
                 last_done_at=at(2026, 8, 16))  # last week -> up for grabs
        add_task(name="Rinse bins", cadence_days=7, assignee_id=None, claimable=True,
                 last_done_at=at(2026, 8, 18))  # this week -> hidden
        _, up_for_grabs = chores_for_user(db, kid.id, now=WED, tz=timezone.utc)
        assert names(up_for_grabs) == {"Sweep porch"}


class TestLocalWeekBoundary:
    def test_boundary_is_the_members_timezone(self, db, kid, add_task):
        # Done 2026-08-17 02:00 UTC = 2026-08-16 22:00 in Eastern (Sunday),
        # i.e. last week locally. UTC would call it "this week" and hide it;
        # the member's local Monday is what counts, so it should show.
        add_task(name="Set the table", cadence_days=7, assignee_id=kid.id,
                 last_done_at=datetime(2026, 8, 17, 2, 0, tzinfo=timezone.utc))
        now = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)

        hidden_utc, _ = chores_for_user(db, kid.id, now=now, tz=timezone.utc)
        assert names(hidden_utc) == set()

        shown_local, _ = chores_for_user(db, kid.id, now=now, tz=EASTERN)
        assert names(shown_local) == {"Set the table"}
