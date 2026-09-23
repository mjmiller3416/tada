"""Schedule (or send) a one-off TEST push to a user's devices, to diagnose
notification delivery without touching any in-app setting.

The scheduled modes insert a plain one-shot Reminder row and let the
production reminder worker (app/cron/reminder_worker.py, the Railway
service named "cron") send it on its HH:MM:00 pass, through exactly the
code path a real nudge takes. Nothing else changes: no Settings row, not
the daily-nudge row, and the test row deactivates itself once sent, just
like a snooze reminder. Every test is numbered ("Tada test #3") and kept
as a row, so `--list` is a log of what was scheduled, when the worker
actually sent it, and what is still pending — compare that with when the
phone showed it.

Run from backend/ with the Railway env injected (DATABASE_URL and the
VAPID keys). The scripts/test-push.ps1 wrapper does that for you:

    .\\scripts\\test-push.ps1 -In 5              # the worker sends it 5 minutes from now
    .\\scripts\\test-push.ps1 -At 15:45          # today at 3:45 PM her local time (tomorrow if past)
    .\\scripts\\test-push.ps1 -Now               # send right now, from this machine
    .\\scripts\\test-push.ps1 -Now -Device apple # ...to one device only (fcm | apple)
    .\\scripts\\test-push.ps1 -List              # every test so far: scheduled vs sent
    .\\scripts\\test-push.ps1 -Cancel            # drop the tests that haven't gone out yet

Or directly: `python -m scripts.test_push --in 5 --user Maryann`. The
recipient is always explicit here, as in send_note.py — the household
has two owners.

pytest never collects this module: pytest.ini limits collection to
tests/, and tests/test_push_script.py imports it as a plain module.
"""

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone, tzinfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.push_subscription import PushSubscription
from app.models.reminder import Reminder
from app.models.user import User
from app.services import reminder_service, settings_service
from app.services.push_service import send_push

#: Every test row's title starts with this, so --list / --cancel find
#: them and nothing else — real reminders are never touched.
TEST_TITLE_PREFIX = "Tada test"

#: Push-service hosts behind --device. Chrome (Android or desktop)
#: subscribes through Google's FCM; Safari, or an iPhone home-screen web
#: app, through Apple.
DEVICE_HOSTS = {"fcm": "fcm.googleapis.com", "apple": "web.push.apple.com"}


def _aware(moment: datetime) -> datetime:
    """SQLite hands back naive UTC datetimes; Postgres aware ones."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


def _clock(local: datetime) -> str:
    """'3:45 PM' — for the notification body."""
    return f"{local.hour % 12 or 12}:{local:%M} {local:%p}"


def _stamp(moment: datetime, tz: tzinfo) -> str:
    """'Fri Sep 05 03:45:00 PM' in the user's zone — for the terminal."""
    return _aware(moment).astimezone(tz).strftime("%a %b %d %I:%M:%S %p")


def device_label(endpoint: str) -> str:
    for label, host in DEVICE_HOSTS.items():
        if host in endpoint:
            return label
    return "other"


def find_user(db: Session, name: str) -> User:
    user = db.scalars(select(User).where(User.name.ilike(name))).first()
    if user is None:
        raise SystemExit(f"No user named {name!r} found")
    return user


def test_rows(db: Session, user_id: int) -> list[Reminder]:
    return list(
        db.scalars(
            select(Reminder)
            .where(
                Reminder.user_id == user_id,
                Reminder.title.like(f"{TEST_TITLE_PREFIX}%"),
            )
            .order_by(Reminder.id)
        ).all()
    )


def next_test_number(db: Session, user_id: int) -> int:
    return len(test_rows(db, user_id)) + 1


def resolve_in(minutes: int, now: datetime) -> datetime:
    """`--in N`: N minutes from now, floored to the minute, so the
    worker's HH:MM:00 pass finds it due exactly then and the "worker
    lag" in --list is a clean number."""
    return (now + timedelta(minutes=minutes)).replace(second=0, microsecond=0)


def resolve_at(hhmm: str, tz_name: str, now: datetime) -> datetime:
    """`--at HH:MM`: the next moment the user's local clock reads HH:MM —
    today if that is still ahead, otherwise tomorrow."""
    if not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", hhmm):
        raise SystemExit(f"--at wants HH:MM (24-hour clock), got {hhmm!r}")
    return reminder_service.next_nudge_occurrence(hhmm, tz_name, now)


def schedule_test(
    db: Session, user: User, when: datetime, tz: tzinfo, body: str | None = None
) -> Reminder:
    """Insert the one-shot row the worker will send at `when` (UTC).
    Caller commits."""
    number = next_test_number(db, user.id)
    reminder = Reminder(
        user_id=user.id,
        title=f"{TEST_TITLE_PREFIX} #{number} 🔔",
        body=body
        or f"Scheduled for {_clock(when.astimezone(tz))}. Note when it actually showed up 💛",
        scheduled_for=when,
        active=True,
    )
    db.add(reminder)
    db.flush()
    return reminder


def send_now(
    db: Session,
    user: User,
    device: str,
    tz: tzinfo,
    body: str | None = None,
    now: datetime | None = None,
) -> list[tuple[str, bool]]:
    """Push straight from this machine, to every device or one of them,
    and record the test as an already-sent row so --list keeps the full
    log and the numbering stays in step. Caller commits. Returns one
    (device label, delivered) pair per push attempted."""
    now = now or datetime.now(timezone.utc)
    subscriptions = db.scalars(
        select(PushSubscription)
        .where(PushSubscription.user_id == user.id)
        .order_by(PushSubscription.id)
    ).all()
    if device != "all":
        subscriptions = [s for s in subscriptions if DEVICE_HOSTS[device] in s.endpoint]
    if not subscriptions:
        raise SystemExit(f"{user.name} has no push subscription for device {device!r}")

    number = next_test_number(db, user.id)
    title = f"{TEST_TITLE_PREFIX} #{number} 🔔"
    text = body or (
        f"Sent at {_clock(now.astimezone(tz))} straight from the laptop. "
        "Note when it showed up 💛"
    )
    results = [
        (device_label(s.endpoint), send_push(s, title=title, body=text, db=db))
        for s in subscriptions
    ]
    db.add(
        Reminder(
            user_id=user.id,
            title=title,
            body=text,
            scheduled_for=now,
            last_sent_at=now,
            active=False,
        )
    )
    db.flush()
    return results


def cancel_pending(db: Session, user: User) -> list[Reminder]:
    """Deactivate the test rows the worker hasn't sent yet — only those.
    Caller commits."""
    pending = [row for row in test_rows(db, user.id) if row.active]
    for row in pending:
        row.active = False
    return pending


def describe(rows: list[Reminder], tz: tzinfo) -> list[str]:
    lines = []
    for row in rows:
        if row.last_sent_at is not None:
            lag = (_aware(row.last_sent_at) - _aware(row.scheduled_for)).total_seconds()
            status = f"sent {_stamp(row.last_sent_at, tz)} (worker lag {lag:.1f} s)"
        elif row.active:
            status = "pending"
        else:
            status = "cancelled"
        lines.append(
            f"{row.title}  id {row.id}  scheduled {_stamp(row.scheduled_for, tz)}  {status}"
        )
    return lines


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Schedule or send a one-off TEST push (delivery diagnosis)"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--in", dest="in_minutes", type=int, metavar="MINUTES",
        help="the worker sends it this many minutes from now (0 = its next pass)",
    )
    mode.add_argument("--at", metavar="HH:MM", help="the worker sends it at this local time")
    mode.add_argument("--now", action="store_true", help="send right now, from this machine")
    mode.add_argument("--list", action="store_true", help="show every test: scheduled vs sent")
    mode.add_argument("--cancel", action="store_true", help="drop the tests not yet sent")
    parser.add_argument("--user", required=True, help="recipient's name")
    parser.add_argument(
        "--device", choices=["all", *DEVICE_HOSTS], default="all",
        help="with --now only: push to one of the user's devices",
    )
    parser.add_argument("--body", help="replace the default notification text")
    args = parser.parse_args(argv)
    if args.device != "all" and not args.now:
        parser.error("--device only applies with --now; the worker always sends to every device")
    if args.in_minutes is not None and args.in_minutes < 0:
        parser.error("--in wants a number of minutes from now, 0 or more")

    # The titles carry emoji; a Windows console often can't.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    db = SessionLocal()
    try:
        user = find_user(db, args.user)
        tz_name = settings_service.get_setting(db, user.id, "timezone")
        tz = settings_service.user_timezone(db, user.id)
        now = datetime.now(timezone.utc)

        if args.list:
            rows = test_rows(db, user.id)
            print(f"{len(rows)} test(s) for {user.name} (times in {tz_name}):")
            for line in describe(rows, tz):
                print("  " + line)
            return

        if args.cancel:
            cancelled = cancel_pending(db, user)
            db.commit()
            print(f"Cancelled {len(cancelled)} pending test(s) for {user.name}.")
            return

        if args.now:
            results = send_now(db, user, args.device, tz, body=args.body, now=now)
            db.commit()
            for label, delivered in results:
                print(f"{label}: {'accepted by the push service' if delivered else 'FAILED'}")
            return

        if args.in_minutes is not None:
            when = resolve_in(args.in_minutes, now)
        else:
            when = resolve_at(args.at, tz_name, now)

        devices = db.scalar(
            select(PushSubscription.id).where(PushSubscription.user_id == user.id).limit(1)
        )
        if devices is None:
            print(f"Note: {user.name} has no push subscriptions; the worker will log 0 push(es).")
        if settings_service.is_on_vacation(db, user.id, now.astimezone(tz).date()):
            print(
                f"Note: {user.name} is in vacation mode; the worker defers reminders a day at "
                "a time until it ends, this test included."
            )

        reminder = schedule_test(db, user, when, tz, body=args.body)
        db.commit()
        print(
            f"Scheduled {reminder.title} (reminder id {reminder.id}) for "
            f"{_stamp(when, tz)} {tz_name}, {when:%H:%M} UTC."
        )
        print(
            "The worker sends it on that minute's pass — watch with "
            "`railway logs --service cron -n 20`, then compare with when the phone showed it."
        )
        print("`--list` shows the exact send time afterwards.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
