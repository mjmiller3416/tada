from pydantic import BaseModel

from app.schemas.tasks import TaskRead


class ChoresResponse(BaseModel):
    """The kid home surface (SPEC §6 multi-user): chores assigned to me,
    plus unassigned ones the owner left open to claim."""

    mine: list[TaskRead]
    up_for_grabs: list[TaskRead]
    # Parent check: my chores that are done and waiting for a parent to
    # look (check_status "ready"). Additive — older clients ignore it.
    waiting_for_check: list[TaskRead] = []
