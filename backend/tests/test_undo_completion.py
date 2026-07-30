"""Tests for undo_completion (Phase 9): undo reverses the DECAY STATE
ONLY. It restores last_done_at exactly (NULL preserved as NULL), deletes
the CompletionLog row, and touches nothing else — streaks only ever go
up, badges are never revoked, and a snooze cleared by completion stays
cleared. Scoped to today's completions; older history belongs to the
Phase 4.6 last-done editor.

The owner fixture pins her timezone to UTC, so "today" in the undo
window lines up exactly with the UTC timestamps used below.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import CompletionLog
from app.models.badge import Badge, UserBadge
from app.services.scheduling import (
    UndoWindowClosed,
    band_for_ratio,
    complete_task,
    dirtiness_ratio,
    undo_completion,
)

NOW = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)


def days_ago(days: float) -> datetime:
    return NOW - timedelta(days=days)


def _add_task(db, make_task, **overrides):
    overrides.setdefault("cadence_days", 7)
    overrides.setdefault("last_done_at", days_ago(10))  # ratio 10/7, overdue
    task = make_task(**overrides)
    db.add(task)
    db.flush()
    return task


class TestUndoRestoresDecayState:
    def test_restores_the_exact_previous_last_done_at(self, db, make_task, owner):
        task = _add_task(db, make_task, last_done_at=days_ago(3))
        log = complete_task(db, task, owner, "direct", NOW)
        assert task.last_done_at == NOW
        undo_completion(db, log, NOW)
        assert task.last_done_at == days_ago(3)

    def test_first_ever_completion_undoes_back_to_never_done(self, db, make_task, owner):
        task = _add_task(db, make_task, last_done_at=None)
        log = complete_task(db, task, owner, "direct", NOW)
        undo_completion(db, log, NOW)
        assert task.last_done_at is None  # NULL preserved — correct, not a bug

    def test_deletes_the_log_row(self, db, make_task, owner):
        task = _add_task(db, make_task)
        log = complete_task(db, task, owner, "direct", NOW)
        undo_completion(db, log, NOW)
        rows = db.scalars(
            select(CompletionLog).where(CompletionLog.task_id == task.id)
        ).all()
        assert rows == []

    def test_round_trip_ratio_and_band_match_exactly(self, db, make_task, owner):
        """The test that matters most: complete + undo returns the task
        to exactly the priority it had — as if the mis-tap never happened."""
        task = _add_task(db, make_task, last_done_at=days_ago(10))
        before_ratio = dirtiness_ratio(task, NOW)
        before_band = band_for_ratio(before_ratio)
        log = complete_task(db, task, owner, "direct", NOW)
        undo_completion(db, log, NOW)
        assert dirtiness_ratio(task, NOW) == before_ratio
        assert band_for_ratio(dirtiness_ratio(task, NOW)) == before_band


class TestUndoTouchesNothingElse:
    def test_streak_fields_are_left_untouched(self, db, make_task, owner):
        task = _add_task(db, make_task)
        log = complete_task(db, task, owner, "direct", NOW)
        streak = owner.current_streak
        longest = owner.longest_streak
        active = owner.last_active_date
        assert streak == 1  # the completion moved it; undo must not
        undo_completion(db, log, NOW)
        assert owner.current_streak == streak
        assert owner.longest_streak == longest
        assert owner.last_active_date == active

    def test_a_badge_earned_by_the_completion_is_not_revoked(self, db, make_task, owner):
        task = _add_task(db, make_task)
        log = complete_task(db, task, owner, "direct", NOW)
        first_task = db.scalar(select(Badge).where(Badge.code == "first_task"))
        assert (
            db.scalar(
                select(UserBadge).where(
                    UserBadge.user_id == owner.id, UserBadge.badge_id == first_task.id
                )
            )
            is not None
        )
        undo_completion(db, log, NOW)
        assert (
            db.scalar(
                select(UserBadge).where(
                    UserBadge.user_id == owner.id, UserBadge.badge_id == first_task.id
                )
            )
            is not None
        )  # earned once, never revoked (SPEC §5)

    def test_a_snooze_cleared_by_completion_stays_cleared(self, db, make_task, owner):
        task = _add_task(db, make_task, snoozed_until=NOW + timedelta(days=3))
        log = complete_task(db, task, owner, "direct", NOW)
        assert task.snoozed_until is None
        undo_completion(db, log, NOW)
        assert task.snoozed_until is None  # she can snooze again in a tap


class TestUndoWindow:
    def test_refused_for_a_completion_from_a_previous_day(self, db, make_task, owner):
        task = _add_task(db, make_task)
        log = complete_task(db, task, owner, "direct", days_ago(1))
        with pytest.raises(UndoWindowClosed):
            undo_completion(db, log, NOW)
        # Refusal changes nothing: the completion and its effect stand.
        assert task.last_done_at == days_ago(1)
        rows = db.scalars(
            select(CompletionLog).where(CompletionLog.task_id == task.id)
        ).all()
        assert len(rows) == 1

    def test_allowed_late_on_the_same_local_day(self, db, make_task, owner):
        task = _add_task(db, make_task)
        morning = NOW.replace(hour=0, minute=5)
        log = complete_task(db, task, owner, "direct", morning)
        undo_completion(db, log, NOW.replace(hour=23, minute=55))
        assert task.last_done_at == days_ago(10)
