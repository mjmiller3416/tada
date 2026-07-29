"""Tests for complete_task (SPEC §4): completion resets the decay curve,
clears any snooze, and writes the permanent CompletionLog row. Phase 5
rides the same seam, so the streak assertions live here too — every
completion path counts exactly once.

The owner fixture pins her timezone to UTC so "a day" in the streak math
lines up exactly with the UTC timestamps used below.
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.models import CompletionLog
from app.services.scheduling import complete_task, dirtiness_ratio

NOW = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)


def days_ago(days: float) -> datetime:
    return NOW - timedelta(days=days)


def _add_task(db, make_task, **overrides):
    overrides.setdefault("cadence_days", 7)
    overrides.setdefault("last_done_at", days_ago(14))  # ratio 2.0
    task = make_task(**overrides)
    db.add(task)
    db.flush()
    return task


class TestCompleteTask:
    def test_resets_the_decay_curve(self, db, make_task, owner):
        task = _add_task(db, make_task)
        assert dirtiness_ratio(task, NOW) == 2.0
        complete_task(db, task, owner, "direct", NOW)
        assert task.last_done_at == NOW
        assert dirtiness_ratio(task, NOW) == 0.0

    def test_clears_any_snooze(self, db, make_task, owner):
        task = _add_task(db, make_task, snoozed_until=NOW + timedelta(days=3))
        complete_task(db, task, owner, "direct", NOW)
        assert task.snoozed_until is None

    def test_writes_a_completion_log_row(self, db, make_task, owner):
        task = _add_task(db, make_task)
        log = complete_task(db, task, owner, "focus_session", NOW)
        assert log.id is not None  # flushed, not just pending
        rows = db.scalars(
            select(CompletionLog).where(CompletionLog.task_id == task.id)
        ).all()
        assert len(rows) == 1
        assert rows[0] is log
        assert log.completed_by == owner.id
        assert log.completed_at == NOW
        assert log.source == "focus_session"

    def test_every_completion_writes_its_own_log(self, db, make_task, owner):
        task = _add_task(db, make_task)
        complete_task(db, task, owner, "direct", NOW)
        complete_task(db, task, owner, "zone", NOW + timedelta(hours=2))
        sources = db.scalars(
            select(CompletionLog.source).where(CompletionLog.task_id == task.id)
        ).all()
        assert sorted(sources) == ["direct", "zone"]


class TestStreakSeam:
    """Phase 5 wired streaks into the complete_task seam — the fields sat
    at 0 for four phases before that. These tests pin the seam itself;
    the full streak rules (grace day, vacation freeze) live in
    services/streaks.py."""

    def test_first_completion_starts_the_streak(self, db, make_task, owner):
        task = _add_task(db, make_task)
        assert owner.current_streak == 0 and owner.last_active_date is None
        complete_task(db, task, owner, "direct", NOW)
        assert owner.current_streak == 1
        assert owner.longest_streak == 1
        assert owner.last_active_date == date(2026, 7, 1)

    def test_second_completion_same_day_changes_nothing(self, db, make_task, owner):
        first = _add_task(db, make_task)
        second = _add_task(db, make_task, name="Sweep floor")
        complete_task(db, first, owner, "direct", NOW)
        complete_task(db, second, owner, "direct", NOW + timedelta(hours=3))
        assert owner.current_streak == 1
        assert owner.last_active_date == date(2026, 7, 1)

    def test_next_day_completion_grows_the_streak(self, db, make_task, owner):
        task = _add_task(db, make_task)
        complete_task(db, task, owner, "direct", NOW)
        complete_task(db, task, owner, "direct", NOW + timedelta(days=1))
        assert owner.current_streak == 2
        assert owner.longest_streak == 2
        assert owner.last_active_date == date(2026, 7, 2)
