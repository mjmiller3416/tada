from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.campaign import Campaign, CampaignTask
from app.models.task import Task
from app.models.user import User
from app.routers.auth import require_owner
from app.schemas.campaigns import (
    CampaignCreate,
    CampaignDetail,
    CampaignRead,
    CampaignUpdate,
    campaign_to_detail,
    campaign_to_read,
)
from app.services import zones as zone_service

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


def _get_campaign(db: Session, campaign_id: int) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign not found")
    return campaign


def _check_task_ids(db: Session, task_ids: list[int]) -> None:
    unique = set(task_ids)
    found = db.scalars(select(Task.id).where(Task.id.in_(unique))).all()
    if len(found) != len(unique):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Task not found")


@router.get("", response_model=list[CampaignRead])
def list_campaigns(
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> list[CampaignRead]:
    """All campaigns with their progress rollups — running ones first,
    then upcoming/paused by start date, newest first within that."""
    today = zone_service.local_today(db, current_user.id)
    campaigns = db.scalars(select(Campaign)).all()
    reads = [campaign_to_read(c, today) for c in campaigns]
    reads.sort(key=lambda c: (not c.is_running, c.start_date.toordinal() * -1))
    return reads


@router.post("", response_model=CampaignDetail, status_code=status.HTTP_201_CREATED)
def create_campaign(
    payload: CampaignCreate,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> CampaignDetail:
    """Create a campaign (SPEC §6). It starts inactive — activating it is
    the explicit opt-in that puts it on the home screen."""
    _check_task_ids(db, payload.task_ids)
    campaign = Campaign(
        name=payload.name,
        season=payload.season,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    campaign.task_links = [
        CampaignTask(task_id=task_id) for task_id in dict.fromkeys(payload.task_ids)
    ]
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign_to_detail(campaign, zone_service.local_today(db, current_user.id))


@router.get("/{campaign_id}", response_model=CampaignDetail)
def get_campaign(
    campaign_id: int,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> CampaignDetail:
    campaign = _get_campaign(db, campaign_id)
    return campaign_to_detail(campaign, zone_service.local_today(db, current_user.id))


@router.patch("/{campaign_id}", response_model=CampaignDetail)
def update_campaign(
    campaign_id: int,
    payload: CampaignUpdate,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> CampaignDetail:
    """Edit a campaign; `task_ids` replaces the checklist but keeps the
    done flag of any task that stays on it. Toggling `active` off cleanly
    shelves the overlay — the tasks themselves are untouched and keep
    decaying as usual."""
    campaign = _get_campaign(db, campaign_id)

    if payload.name is not None:
        campaign.name = payload.name
    if payload.season is not None:
        campaign.season = payload.season or None
    if payload.start_date is not None:
        campaign.start_date = payload.start_date
    if payload.end_date is not None:
        campaign.end_date = payload.end_date
    if campaign.end_date < campaign.start_date:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "end_date must be on or after start_date"
        )
    if payload.active is not None:
        campaign.active = payload.active
    if payload.task_ids is not None:
        _check_task_ids(db, payload.task_ids)
        done_by_id = {link.task_id: link.done for link in campaign.task_links}
        campaign.task_links = [
            CampaignTask(task_id=task_id, done=done_by_id.get(task_id, False))
            for task_id in dict.fromkeys(payload.task_ids)
        ]

    db.commit()
    db.refresh(campaign)
    return campaign_to_detail(campaign, zone_service.local_today(db, current_user.id))


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_campaign(
    campaign_id: int,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> None:
    """Deletes the campaign and its checklist only — never the tasks."""
    campaign = _get_campaign(db, campaign_id)
    db.delete(campaign)
    db.commit()
