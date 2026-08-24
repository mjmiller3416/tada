from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.chores import ChoresResponse
from app.schemas.tasks import task_to_read
from app.services import scheduling, settings_service

router = APIRouter(prefix="/api/chores", tags=["chores"])


@router.get("", response_model=ChoresResponse)
def my_chores(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChoresResponse:
    """The kid home surface (SPEC §6 multi-user): my chores plus what's up
    for grabs, both priority-ranked by the same decay engine. Deliberately
    the whole kid API — kids see chores and check them off, nothing more.

    The presentation context (issue #22) keeps the no-debt rule on this
    surface too: a zone mission assigned to a kid shows as quietly
    waiting outside its zone week, never as red debt. Zones and lanes
    are household config living on the owner's settings — a kid has
    none — so the context is built from the primary owner, the same
    clock the zone weeks themselves derive from."""
    tz = settings_service.user_timezone(db, current_user.id)
    mine, up_for_grabs = scheduling.chores_for_user(db, current_user.id, tz=tz)
    owner = db.scalar(select(User).where(User.role == "owner").order_by(User.id))
    ctx = (
        scheduling.presentation_context(
            db, owner.id, tz=settings_service.user_timezone(db, owner.id)
        )
        if owner
        else None
    )
    return ChoresResponse(
        mine=[task_to_read(t, ctx=ctx) for t in mine],
        up_for_grabs=[task_to_read(t, ctx=ctx) for t in up_for_grabs],
    )
