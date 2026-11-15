from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.task import Task
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.chores import ChoresResponse
from app.schemas.tasks import task_to_read
from app.services import parent_check, scheduling, settings_service

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
    # Parent check: what's waiting for a parent to look at, and what came
    # back. A waiting chore is fresh (its decay reset when it was done),
    # so it isn't in `mine`; it gets its own list. A sent-back chore is
    # due again, so it IS in `mine`, carrying the note.
    pending = parent_check.pending_states(db)
    waiting_ids = [
        task_id
        for task_id, log in pending.items()
        if log.check_status == parent_check.READY
    ]
    waiting_tasks = (
        db.scalars(
            select(Task)
            .options(joinedload(Task.room))
            .where(Task.id.in_(waiting_ids), Task.is_active.is_(True))
            .order_by(Task.name)
        ).all()
        if waiting_ids
        else []
    )
    # A chore that is due again already (a weekly chore finished last
    # week, still unchecked on Monday) shows once, in `mine`.
    listed = {t.id for t in mine} | {t.id for t in up_for_grabs}
    waiting = [
        t
        for t in waiting_tasks
        if t.id not in listed
        and (
            t.assignee_id == current_user.id
            or pending[t.id].completed_by == current_user.id
        )
    ]

    def sent_back(task: Task):
        """The send-back note rides on a due chore; "ready" doesn't."""
        log = pending.get(task.id)
        return log if log is not None and log.check_status == parent_check.SENT_BACK else None
    owner = db.scalar(select(User).where(User.role == "owner").order_by(User.id))
    ctx = (
        scheduling.presentation_context(
            db, owner.id, tz=settings_service.user_timezone(db, owner.id)
        )
        if owner
        else None
    )
    return ChoresResponse(
        mine=[task_to_read(t, ctx=ctx, check=sent_back(t)) for t in mine],
        up_for_grabs=[
            task_to_read(t, ctx=ctx, check=sent_back(t)) for t in up_for_grabs
        ],
        waiting_for_check=[
            task_to_read(t, ctx=ctx, check=pending.get(t.id)) for t in waiting
        ],
    )
