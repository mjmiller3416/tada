"""Tests for the cron's `_process` after the issue #24 restructure: it
must mutate reminder state and return PushJobs WITHOUT touching the
network — delivery happens post-commit in `run`, so a crash or push
failure can never roll back state that already produced a notification.
Also pins the per-type TTLs from issue #35.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import app.cron.send_reminders as cron
from app.cron.send_reminders import (
    DAILY_NUDGE_TAG,
    SESSION_TIMER_TAG,
    SESSION_TIMER_TTL,
    _end_of_day_ttl,
    _process,
)
from app.models import Setting
from app.models.reminder import Reminder
from app.services.push_service import DEFAULT_TTL

NOW = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)


def _add_reminder(db, owner, **overrides):
    fields = dict(
        user_id=owner.id,
        title="Ready when you are 💛",
        body="Wipe counters is back on the list — no rush.",
        scheduled_for=NOW - timedelta(hours=1),
        active=True,
        created_at=NOW - timedelta(days=1),
    )
    fields.update(overrides)
    reminder = Reminder(**fields)
    db.add(reminder)
    db.flush()
    return reminder


class TestProcessNeverSends:
    def test_process_makes_no_push_calls(self, db, owner, monkeypatch):
        """The whole point of the restructure: _process decides, run
        delivers. A push call from inside _process would reintroduce the
        send-before-commit spam bug."""

        def bomb(*args, **kwargs):
            raise AssertionError("_process must not send pushes")

        monkeypatch.setattr(cron, "push_to_user", bomb)
        reminder = _add_reminder(db, owner, recurrence_rule="daily")
        jobs = _process(db, reminder, NOW)  # would raise if it sent
        assert len(jobs) == 1


class TestSessionTimer:
    def test_fires_once_with_a_short_ttl(self, db, owner):
        reminder = _add_reminder(
            db, owner, recurrence_rule="session_timer:15", title="That's 15 minutes 🎉"
        )
        jobs = _process(db, reminder, NOW)
        assert reminder.active is False
        assert reminder.last_sent_at == NOW
        assert len(jobs) == 1
        assert jobs[0].tag == SESSION_TIMER_TAG
        assert jobs[0].ttl == SESSION_TIMER_TTL
        assert jobs[0].title == "That's 15 minutes 🎉"


class TestSnoozeReminder:
    def test_sends_when_the_task_is_still_waiting(self, db, make_task, owner):
        task = make_task(last_done_at=None)
        db.add(task)
        db.flush()
        reminder = _add_reminder(db, owner, task_id=task.id)
        jobs = _process(db, reminder, NOW)
        assert reminder.active is False
        assert reminder.last_sent_at == NOW
        assert len(jobs) == 1
        assert jobs[0].ttl == DEFAULT_TTL

    def test_drops_silently_when_the_task_got_done(self, db, make_task, owner):
        """SPEC §5: never nag about finished work — no push at all."""
        task = make_task(last_done_at=NOW - timedelta(hours=2))
        db.add(task)
        db.flush()
        reminder = _add_reminder(db, owner, task_id=task.id)  # created a day ago
        jobs = _process(db, reminder, NOW)
        assert jobs == []
        assert reminder.active is False
        assert reminder.last_sent_at is None


class TestDailyNudge:
    def test_sends_and_rolls_to_the_next_occurrence(self, db, owner):
        reminder = _add_reminder(db, owner, recurrence_rule="daily", body="")
        jobs = _process(db, reminder, NOW)
        assert len(jobs) == 1
        assert jobs[0].tag == DAILY_NUDGE_TAG
        # Bounded by the local day (issue #35): never 0, never past
        # midnight.
        assert 60 <= jobs[0].ttl <= 24 * 60 * 60
        assert reminder.active is True
        assert reminder.last_sent_at == NOW
        # advance_daily_nudge computes from the real clock; "strictly in
        # the future" is the contract that matters.
        assert reminder.scheduled_for > datetime.now(timezone.utc)


class TestVacation:
    def test_defers_without_deactivating_and_sends_nothing(self, db, owner):
        db.add(Setting(user_id=owner.id, key="vacation_until", value="2100-01-01"))
        db.flush()
        reminder = _add_reminder(db, owner, scheduled_for=NOW - timedelta(hours=2))
        jobs = _process(db, reminder, NOW)
        assert jobs == []
        assert reminder.active is True  # resumes by itself, never dropped
        assert reminder.scheduled_for > NOW


class TestEndOfDayTtl:
    def test_stays_within_the_local_day(self):
        for tz in (timezone.utc, ZoneInfo("America/New_York")):
            ttl = _end_of_day_ttl(tz)
            assert 60 <= ttl <= 24 * 60 * 60
