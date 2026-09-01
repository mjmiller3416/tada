import json
import logging

from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.push_subscription import PushSubscription
from app.models.user import User

logger = logging.getLogger(__name__)

#: How long the push service may queue an undelivered notification, in
#: seconds. pywebpush's default is ttl=0 — "deliver this instant or
#: discard" — which silently dropped every push sent while her phone was
#: dozing (issue #35). Six hours covers a one-shot reminder's useful
#: life; time-critical sends pass their own (the cron's session timer
#: and end-of-day-bounded daily nudge).
DEFAULT_TTL = 6 * 60 * 60

#: Seconds before giving up on the push service's HTTP endpoint. Without
#: it the underlying requests.post can wait forever — hanging a kid's
#: completion request, or stalling an entire cron run on one bad
#: endpoint (issue #24). The Enchanted Spoon and GitHub clients already set
#: explicit timeouts; this brings the third outbound client in line.
SEND_TIMEOUT = 10


def send_push(
    subscription: PushSubscription,
    title: str,
    body: str,
    db: Session,
    tag: str | None = None,
    ttl: int = DEFAULT_TTL,
) -> bool:
    """Sends one Web Push notification. Returns False (and removes the
    subscription) if the push service reports it's gone/expired, which is
    the normal way subscriptions die — no manual cleanup needed elsewhere.

    `tag` rides the payload for the service worker's showNotification:
    notifications sharing a tag replace each other instead of stacking
    (used by the daily nudge).

    Every send carries `Urgency: high` — all Tada pushes are user-facing
    notifications, and normal urgency lets Android defer them while the
    phone dozes, which combined with a short TTL means they never arrive
    at all (issue #35).

    Never raises: a push is always best-effort, and no caller — a kid's
    completion request, the cron loop — should ever fail because the
    push layer did (issue #24).
    """
    subscription_info = {
        "endpoint": subscription.endpoint,
        "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
    }

    payload: dict[str, str] = {"title": title, "body": body}
    if tag:
        payload["tag"] = tag

    try:
        webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": f"mailto:{settings.vapid_claims_email}"},
            ttl=ttl,
            timeout=SEND_TIMEOUT,
            headers={"Urgency": "high"},
        )
        return True
    except WebPushException as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        if status_code in (404, 410):
            logger.info("Push subscription %s is gone, removing", subscription.id)
            db.delete(subscription)
            db.commit()
        else:
            logger.error("Push send failed: %s", exc)
        return False
    except Exception:
        # pywebpush/py-vapid raise plain ValueErrors for malformed or
        # empty VAPID keys, and requests has its own network errors —
        # none of them may escape into the caller.
        logger.exception("Push send failed for subscription %s", subscription.id)
        return False


def push_to_user(
    db: Session,
    user_id: int,
    title: str,
    body: str,
    tag: str | None = None,
    ttl: int = DEFAULT_TTL,
) -> int:
    """Push to every subscription (phone + Chromebook) a user has.
    Returns how many sends succeeded."""
    subscriptions = db.scalars(
        select(PushSubscription).where(PushSubscription.user_id == user_id)
    ).all()
    return sum(
        1
        for subscription in subscriptions
        if send_push(subscription, title=title, body=body, db=db, tag=tag, ttl=ttl)
    )


def notify_owners(db: Session, title: str, body: str) -> None:
    """Notify every owner-role user (in practice, exactly one) — used when
    a kid checks off a chore (SPEC §6 multi-user)."""
    owner_ids = db.scalars(select(User.id).where(User.role == "owner")).all()
    for owner_id in owner_ids:
        push_to_user(db, owner_id, title, body)
