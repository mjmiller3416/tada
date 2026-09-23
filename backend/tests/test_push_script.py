"""Tests for scripts/test_push.py, the delivery-diagnosis script: a
scheduled test is a plain one-shot reminder the engine sends exactly like
a snooze; --now honours --device and leaves a log row; --list/--cancel
only ever touch test rows, never a real reminder."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.cron.send_reminders import _process
from app.models.push_subscription import PushSubscription
from app.models.reminder import Reminder
from scripts import test_push

UTC = timezone.utc
NOW = datetime(2026, 9, 5, 15, 43, 20, tzinfo=UTC)  # 11:43:20 in New York


class TestResolve:
    def test_in_floors_to_the_minute(self):
        assert test_push.resolve_in(2, NOW) == datetime(2026, 9, 5, 15, 45, tzinfo=UTC)

    def test_in_zero_is_this_minute(self):
        assert test_push.resolve_in(0, NOW) == datetime(2026, 9, 5, 15, 43, tzinfo=UTC)

    def test_at_is_today_when_still_ahead(self):
        when = test_push.resolve_at("12:30", "America/New_York", NOW)
        assert when == datetime(2026, 9, 5, 16, 30, tzinfo=UTC)

    def test_at_rolls_to_tomorrow_when_already_past(self):
        when = test_push.resolve_at("08:30", "America/New_York", NOW)
        assert when == datetime(2026, 9, 6, 12, 30, tzinfo=UTC)

    def test_at_rejects_anything_but_hh_mm(self):
        with pytest.raises(SystemExit):
            test_push.resolve_at("8pm", "America/New_York", NOW)


class TestScheduledRow:
    def test_engine_sends_it_once_like_a_snooze(self, db, owner):
        when = test_push.resolve_in(2, NOW)
        reminder = test_push.schedule_test(db, owner, when, UTC)
        db.commit()
        assert reminder.title == "Tada test #1 🔔"
        assert reminder.active is True

        jobs = _process(db, reminder, when)
        assert len(jobs) == 1
        assert jobs[0].title == reminder.title
        assert jobs[0].tag is None  # tests stack in the tray, never replace each other
        assert reminder.active is False
        assert reminder.last_sent_at == when

    def test_numbers_count_only_test_rows(self, db, owner):
        db.add(
            Reminder(
                user_id=owner.id,
                title="Ready when you are 💛",
                body="",
                scheduled_for=NOW,
                active=True,
            )
        )
        db.flush()
        first = test_push.schedule_test(db, owner, NOW, UTC)
        second = test_push.schedule_test(db, owner, NOW, UTC)
        assert (first.title, second.title) == ("Tada test #1 🔔", "Tada test #2 🔔")

    def test_body_names_the_local_time(self, db, owner):
        when = datetime(2026, 9, 5, 19, 45, tzinfo=UTC)
        reminder = test_push.schedule_test(db, owner, when, ZoneInfo("America/New_York"))
        assert "3:45 PM" in reminder.body

    def test_custom_body_wins(self, db, owner):
        reminder = test_push.schedule_test(db, owner, NOW, UTC, body="Ping from the laptop")
        assert reminder.body == "Ping from the laptop"


class TestCancel:
    def test_only_pending_test_rows_are_touched(self, db, owner):
        real = Reminder(
            user_id=owner.id,
            title="Good morning ☀️",
            body="",
            scheduled_for=NOW,
            recurrence_rule="daily",
            active=True,
        )
        db.add(real)
        db.flush()
        pending = test_push.schedule_test(db, owner, NOW, UTC)
        sent = test_push.schedule_test(db, owner, NOW, UTC)
        sent.active = False
        sent.last_sent_at = NOW

        cancelled = test_push.cancel_pending(db, owner)
        assert [row.id for row in cancelled] == [pending.id]
        assert pending.active is False
        assert real.active is True


class TestSendNow:
    @pytest.fixture()
    def two_devices(self, db, owner):
        for endpoint in (
            "https://fcm.googleapis.com/fcm/send/abc",
            "https://web.push.apple.com/QWxx",
        ):
            db.add(
                PushSubscription(
                    user_id=owner.id, endpoint=endpoint, p256dh="p", auth="a", created_at=NOW
                )
            )
        db.flush()

    def test_device_filter_targets_one_endpoint(self, db, owner, two_devices, monkeypatch):
        reached: list[str] = []

        def fake_send_push(subscription, title, body, db, **kwargs):
            reached.append(subscription.endpoint)
            return True

        monkeypatch.setattr(test_push, "send_push", fake_send_push)
        results = test_push.send_now(db, owner, "apple", UTC, now=NOW)
        assert reached == ["https://web.push.apple.com/QWxx"]
        assert results == [("apple", True)]

    def test_all_devices_and_a_log_row(self, db, owner, two_devices, monkeypatch):
        monkeypatch.setattr(test_push, "send_push", lambda *args, **kwargs: True)
        results = test_push.send_now(db, owner, "all", UTC, now=NOW)
        assert [label for label, _ in results] == ["fcm", "apple"]

        rows = test_push.test_rows(db, owner.id)
        assert len(rows) == 1
        assert rows[0].title == "Tada test #1 🔔"
        assert rows[0].active is False  # the worker must never pick it up
        assert test_push._aware(rows[0].last_sent_at) == NOW  # SQLite hands back naive
        assert test_push.describe(rows, UTC)[0].endswith("(worker lag 0.0 s)")

    def test_no_matching_device_is_an_error(self, db, owner):
        with pytest.raises(SystemExit):
            test_push.send_now(db, owner, "apple", UTC, now=NOW)


class TestDescribe:
    def test_pending_and_cancelled_and_sent(self, db, owner):
        pending = test_push.schedule_test(db, owner, NOW, UTC)
        cancelled = test_push.schedule_test(db, owner, NOW, UTC)
        cancelled.active = False
        sent = test_push.schedule_test(db, owner, NOW, UTC)
        sent.active = False
        sent.last_sent_at = datetime(2026, 9, 5, 15, 43, 21, tzinfo=UTC)

        lines = test_push.describe([pending, cancelled, sent], UTC)
        assert lines[0].endswith("pending")
        assert lines[1].endswith("cancelled")
        assert lines[2].endswith("(worker lag 1.0 s)")
