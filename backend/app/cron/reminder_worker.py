"""Always-on reminder worker — the Railway service still named `cron`.

Runs `send_reminders.run()` (one stateless pass over the due reminders)
immediately at startup and then at every wall-clock minute, forever.
Deployed with `restartPolicyType: ALWAYS` and NO cron schedule, so Railway
keeps it alive rather than triggering it.

Why a loop and not Railway's cron schedule (2026-09-04): Railway's cron
has a 5-minute floor and skips a trigger whenever it believes the previous
execution is still running. In production the schedule fired exactly once
per git deploy and never again, so every nudge and snooze reminder went
out in a batch at the next deploy — the "inconsistent notifications" that
looked like a phone problem. A plain loop has no scheduler to fall out
with: if the process is alive, reminders go out; if it dies, Railway
restarts it.

Design notes:
- Each pass is the same one-shot `run()` the cron used, so a pass that
  crashes (database blip, push-service outage) is logged and the next
  minute tries again — the loop holds no state of its own (SPEC §2).
- Passes are aligned to minute boundaries so a reminder due at 08:30:00
  goes out at 08:30, not 08:30:47 (the worker could have started at any
  second).
- SIGTERM/SIGINT (Railway's redeploy signal, Ctrl-C locally) end the loop
  after the current pass instead of killing it mid-send. `run()` already
  commits before delivering, so even a hard kill can't re-send.
- `run()`'s advisory lock still guards the redeploy overlap window, when
  the old and new worker are briefly both alive.
"""

import logging
import signal
import threading
import time
from collections.abc import Callable

from app.cron.send_reminders import run

logger = logging.getLogger("cron.reminder_worker")

#: Seconds between passes — the reminder engine's resolution (SPEC §2).
TICK_SECONDS = 60

#: Longest single sleep while waiting for the next tick, so a shutdown
#: request is noticed within about a second.
POLL_SECONDS = 1.0


def seconds_until_next_tick(now: float, tick_seconds: float = TICK_SECONDS) -> float:
    """Seconds from `now` (a Unix timestamp) to the next tick boundary.
    Never zero: exactly on a boundary means a full tick until the next."""
    return tick_seconds - (now % tick_seconds)


def run_forever(
    pass_fn: Callable[[], None] = run,
    *,
    stop: threading.Event | None = None,
    tick_seconds: float = TICK_SECONDS,
    poll_seconds: float = POLL_SECONDS,
    clock: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Run passes until `stop` is set. Returns how many passes ran.

    The first pass runs at once (a restarted worker shouldn't sit idle
    for up to a minute), each later one at the next tick boundary.
    `clock` and `sleep` are injectable so the loop is testable without
    waiting on real minutes.
    """
    if stop is None:
        stop = threading.Event()
    passes = 0
    while not stop.is_set():
        try:
            pass_fn()
        except Exception:
            # One bad pass must never take the worker down — the next
            # minute gets a fresh session and a fresh chance.
            logger.exception("Reminder pass failed; retrying next minute")
        passes += 1

        now = clock()
        deadline = now + seconds_until_next_tick(now, tick_seconds)
        while not stop.is_set():
            remaining = deadline - clock()
            if remaining <= 0:
                break
            sleep(min(remaining, poll_seconds))
    return passes


def _install_signal_handlers(stop: threading.Event) -> None:
    def request_stop(signum: int, _frame: object) -> None:
        logger.info("Signal %d received; finishing the current pass, then stopping", signum)
        stop.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, request_stop)


def main() -> None:
    # No-op if importing send_reminders already configured logging; kept
    # explicit so the worker's own lines are never silently dropped.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stop = threading.Event()
    _install_signal_handlers(stop)
    logger.info("Reminder worker started: one pass now, then every %d s", TICK_SECONDS)
    passes = run_forever(stop=stop)
    logger.info("Reminder worker stopped after %d pass(es)", passes)


if __name__ == "__main__":
    main()
