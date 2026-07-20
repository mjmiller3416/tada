import json
import logging

from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.push_subscription import PushSubscription
from app.models.user import User

logger = logging.getLogger(__name__)


def send_push(subscription: PushSubscription, title: str, body: str, db: Session) -> bool:
    """Sends one Web Push notification. Returns False (and removes the
    subscription) if the push service reports it's gone/expired, which is
    the normal way subscriptions die — no manual cleanup needed elsewhere."""
    subscription_info = {
        "endpoint": subscription.endpoint,
        "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
    }

    try:
        webpush(
            subscription_info=subscription_info,
            data=json.dumps({"title": title, "body": body}),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": f"mailto:{settings.vapid_claims_email}"},
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


def push_to_user(db: Session, user_id: int, title: str, body: str) -> int:
    """Push to every subscription (phone + Chromebook) a user has.
    Returns how many sends succeeded."""
    subscriptions = db.scalars(
        select(PushSubscription).where(PushSubscription.user_id == user_id)
    ).all()
    return sum(
        1
        for subscription in subscriptions
        if send_push(subscription, title=title, body=body, db=db)
    )


def notify_owners(db: Session, title: str, body: str) -> None:
    """Notify every owner-role user (in practice, exactly one) — used when
    a kid checks off a chore (SPEC §6 multi-user)."""
    owner_ids = db.scalars(select(User.id).where(User.role == "owner")).all()
    for owner_id in owner_ids:
        push_to_user(db, owner_id, title, body)
