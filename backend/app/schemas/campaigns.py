from datetime import date

from pydantic import BaseModel, Field, model_validator

from app.models.campaign import Campaign
from app.schemas.tasks import TaskRead, task_to_read
from app.services import campaigns as campaign_service


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    season: str | None = Field(default=None, max_length=50)
    start_date: date
    end_date: date
    task_ids: list[int] = []

    @model_validator(mode="after")
    def check_window(self) -> "CampaignCreate":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    season: str | None = Field(default=None, max_length=50)
    start_date: date | None = None
    end_date: date | None = None
    active: bool | None = None
    #: Full replacement of the checklist. Tasks already ticked off keep
    #: their `done` flag if they stay on the list.
    task_ids: list[int] | None = None


class CampaignTaskEntry(BaseModel):
    """One checklist row: the task (with live decay state) plus the
    campaign's own done flag."""

    task: TaskRead
    done: bool


class CampaignRead(BaseModel):
    """A campaign with its progress rollup (SPEC §6). `is_running` means
    active AND inside the window — the state that surfaces on the home
    screen."""

    id: int
    name: str
    season: str | None
    start_date: date
    end_date: date
    active: bool
    is_running: bool
    total_tasks: int
    done_tasks: int
    percent: int


class CampaignDetail(CampaignRead):
    tasks: list[CampaignTaskEntry]


def campaign_to_read(campaign: Campaign, today: date) -> CampaignRead:
    done, total = campaign_service.progress(campaign)
    return CampaignRead(
        id=campaign.id,
        name=campaign.name,
        season=campaign.season,
        start_date=campaign.start_date,
        end_date=campaign.end_date,
        active=campaign.active,
        is_running=campaign_service.is_running(campaign, today),
        total_tasks=total,
        done_tasks=done,
        percent=round(100 * done / total) if total else 0,
    )


def campaign_to_detail(campaign: Campaign, today: date) -> CampaignDetail:
    base = campaign_to_read(campaign, today)
    entries = [
        CampaignTaskEntry(task=task_to_read(link.task), done=link.done)
        for link in campaign.task_links
        if link.task is not None
    ]
    # Undone first (dirtiest leading), then the ticked-off tail.
    entries.sort(key=lambda e: (e.done, -e.task.ratio))
    return CampaignDetail(**base.model_dump(), tasks=entries)
