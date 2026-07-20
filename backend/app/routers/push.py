from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.push_subscription import PushSubscription
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.push import PushSubscriptionRequest
from app.services.push_service import send_push

router = APIRouter(prefix="/api/push", tags=["push"])


@router.post("/subscribe", status_code=status.HTTP_204_NO_CONTENT)
def subscribe(
    payload: PushSubscriptionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    existing = db.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint)
    )
    if existing is not None:
        existing.user_id = current_user.id
        existing.p256dh = payload.keys.p256dh
        existing.auth = payload.keys.auth
    else:
        db.add(
            PushSubscription(
                user_id=current_user.id,
                endpoint=payload.endpoint,
                p256dh=payload.keys.p256dh,
                auth=payload.keys.auth,
            )
        )
    db.commit()


@router.post("/test", status_code=status.HTTP_204_NO_CONTENT)
def send_test_push(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """TEMPORARY — Phase 0 only, proves the push pipeline end to end.
    Remove this route once Phase 0 is verified (see build prompts)."""
    subscriptions = db.scalars(
        select(PushSubscription).where(PushSubscription.user_id == current_user.id)
    ).all()

    for subscription in subscriptions:
        send_push(
            subscription,
            title="Tada",
            body="This is a test push. If you see this, the pipeline works!",
            db=db,
        )
