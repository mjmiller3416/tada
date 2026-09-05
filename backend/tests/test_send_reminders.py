"""Tests for the cron's `_process` after the issue #24 restructure: it
must mutate reminder state and return PushJobs WITHOUT touching the
network — delivery happens post-commit in `run`, so a crash or push
failure can never roll back state that already produced a notification.
Also pins the per-type TTLs from issue #35, and the stale-reminder rules
that came with the always-on worker: a reminder the engine only reaches
long after it was due (an outage, the cron-era gaps) is never delivered
as if it were on time.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

import app.cron.send_reminders as cron
from app.cron.send_reminders import (
    DAILY_NUDGE_TAG,
    SESSION_TIMER_TAG,
    SESSION_TIMER_TTL,
    _aware,
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
            db,
            owner,
            recurrence_rule="session_timer:15",
            title="That's 15 minutes 🎉",
            scheduled_for=NOW - timedelta(seconds=30),  # one worker tick late
        )
        jobs = _process(db, reminder, NOW)
        assert reminder.active is False
        assert reminder.last_sent_at == NOW
        assert len(jobs) == 1
        assert jobs[0].tag == SESSION_TIMER_TAG
        assert jobs[0].ttl == SESSION_TIMER_TTL
        assert jobs[0].title == "That's 15 minutes 🎉"

    def test_drops_silently_when_long_overdue(self, db, owner):
        """The engine wasn't running when it was due: "that's your 15
        minutes" an hour after she stopped is dropped, never sent."""
        reminder = _add_reminder(
            db, owner, recurrence_rule="session_timer:15", scheduled_for=NOW - timedelta(hours=1)
        )
        jobs = _process(db, reminder, NOW)
        assert jobs == []
        assert reminder.active is False
        assert reminder.last_sent_at is None


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

    def test_late_the_same_day_still_sends(self, db, owner):
        """Due 08:30, engine reaches it at 12:00: merely late, sent."""
        reminder = _add_reminder(
            db, owner, recurrence_rule="daily", body="", scheduled_for=NOW.replace(hour=8, minute=30)
        )
        jobs = _process(db, reminder, NOW)
        assert len(jobs) == 1
        assert reminder.last_sent_at == NOW

    def test_yesterdays_nudge_waits_for_todays_time(self, db, owner):
        """Due yesterday 13:00 and never sent; now 12:00 today. Yesterday's
        "Good morning" is not delivered today — the row is re-anchored to
        today 13:00 and nothing goes out yet."""
        reminder = _add_reminder(
            db,
            owner,
            recurrence_rule="daily",
            body="",
            scheduled_for=(NOW - timedelta(days=1)).replace(hour=13, minute=0),
        )
        jobs = _process(db, reminder, NOW)
        assert jobs == []
        assert reminder.active is True
        assert reminder.last_sent_at is None
        assert _aware(reminder.scheduled_for) == NOW.replace(hour=13, minute=0)

    def test_days_old_nudge_sends_once_as_todays_when_todays_time_has_passed(self, db, owner):
        """Due three days ago at 08:30; now 12:00. Today's 08:30 has passed,
        so exactly one nudge goes out now — today's, late — and the row
        rolls forward. Never a backlog of three."""
        reminder = _add_reminder(
            db,
            owner,
            recurrence_rule="daily",
            body="",
            scheduled_for=(NOW - timedelta(days=3)).replace(hour=8, minute=30),
        )
        jobs = _process(db, reminder, NOW)
        assert len(jobs) == 1
        assert reminder.last_sent_at == NOW
        assert reminder.scheduled_for > datetime.now(timezone.utc)

    def test_earlier_day_is_judged_in_her_timezone(self, db, owner):
        """NOW is 12:00 UTC = 08:00 in New York. A nudge due yesterday at
        08:30 local waits for today's 08:30 local (12:30 UTC), not for a
        UTC day boundary."""
        tz_setting = db.scalar(
            select(Setting).where(Setting.user_id == owner.id, Setting.key == "timezone")
        )
        tz_setting.value = "America/New_York"
        db.flush()
        yesterday_0830_local = datetime(2026, 6, 30, 8, 30, tzinfo=ZoneInfo("America/New_York"))
        reminder = _add_reminder(
            db,
            owner,
            recurrence_rule="daily",
            body="",
            scheduled_for=yesterday_0830_local.astimezone(timezone.utc),
        )
        jobs = _process(db, reminder, NOW)
        assert jobs == []
        assert _aware(reminder.scheduled_for) == datetime(2026, 7, 1, 12, 30, tzinfo=timezone.utc)


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
