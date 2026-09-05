"""Tests for the always-on reminder worker's loop (app/cron/reminder_worker):
it runs a pass immediately, then one per tick aligned to the minute,
survives a pass that raises, and stops promptly when asked (Railway's
SIGTERM). The clock and sleep are injected so no test waits on real time.
"""

import threading

import pytest

from app.cron import reminder_worker as worker


class FakeClock:
    """A Unix-timestamp clock that only moves when the loop sleeps."""

    def __init__(self, start: float) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class TestTickAlignment:
    def test_next_tick_is_the_next_minute_boundary(self):
        assert worker.seconds_until_next_tick(120.0) == 60
        assert worker.seconds_until_next_tick(130.0) == 50
        assert worker.seconds_until_next_tick(179.9) == pytest.approx(0.1)


class TestLoop:
    def test_runs_at_once_then_once_per_minute_on_the_boundary(self):
        clock = FakeClock(start=1000.0)  # 1000 % 60 == 40 -> next boundary 1020
        stop = threading.Event()
        pass_times: list[float] = []

        def one_pass() -> None:
            pass_times.append(clock.now)
            if len(pass_times) == 3:
                stop.set()

        passes = worker.run_forever(one_pass, stop=stop, clock=clock, sleep=clock.sleep)
        assert passes == 3
        assert pass_times == [1000.0, 1020.0, 1080.0]

    def test_a_failing_pass_does_not_stop_the_loop(self, caplog):
        """A database blip or push-service outage in one pass is logged;
        the next minute tries again with a fresh session."""
        clock = FakeClock(start=0.0)
        stop = threading.Event()
        calls: list[int] = []

        def flaky() -> None:
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("db blip")
            stop.set()

        with caplog.at_level("ERROR", logger="cron.reminder_worker"):
            passes = worker.run_forever(flaky, stop=stop, clock=clock, sleep=clock.sleep)
        assert passes == 2
        assert "Reminder pass failed" in caplog.text

    def test_stop_during_the_wait_ends_it_within_one_poll(self):
        """Railway's SIGTERM sets the stop event mid-sleep: the loop must
        notice within a poll slice, not wait out the rest of the minute."""
        clock = FakeClock(start=0.0)
        stop = threading.Event()

        def sleep(seconds: float) -> None:
            clock.sleep(seconds)
            stop.set()

        passes = worker.run_forever(
            lambda: None, stop=stop, clock=clock, sleep=sleep, poll_seconds=1.0
        )
        assert passes == 1
        assert clock.now <= 1.0

    def test_stop_set_before_start_runs_nothing(self):
        stop = threading.Event()
        stop.set()
        passes = worker.run_forever(
            lambda: pytest.fail("must not run"),
            stop=stop,
            clock=FakeClock(0.0),
            sleep=lambda seconds: None,
        )
        assert passes == 0
