from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.chores import ChoresResponse
from app.schemas.tasks import task_to_read
from app.services import scheduling

router = APIRouter(prefix="/api/chores", tags=["chores"])


@router.get("", response_model=ChoresResponse)
def my_chores(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChoresResponse:
    """The kid home surface (SPEC §6 multi-user): my chores plus what's up
    for grabs, both priority-ranked by the same decay engine. Deliberately
    the whole kid API — kids see chores and check them off, nothing more."""
    mine, up_for_grabs = scheduling.chores_for_user(db, current_user.id)
    return ChoresResponse(
        mine=[task_to_read(t) for t in mine],
        up_for_grabs=[task_to_read(t) for t in up_for_grabs],
    )
