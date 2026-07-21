"""Packing routes (Phase 4) — everything lives under /api/packing, in
its own module, so the cleaning core can't be destabilized from here.

Owner-only for v1: the kids' logins don't touch packing. Mutations on
sections/items return the full list detail — packing lists are small,
and one canonical payload keeps the checklist UI trivially in sync.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.packing import PACKING_CATEGORIES, PackingItem, PackingList, PackingSection
from app.models.user import User
from app.routers.auth import require_owner
from app.schemas.packing import (
    PackingItemCreate,
    PackingItemUpdate,
    PackingListCreate,
    PackingListDetail,
    PackingListRead,
    PackingListUpdate,
    PackingSectionCreate,
    PackingSectionUpdate,
    list_to_detail,
    list_to_read,
)
from app.services import packing as packing_service

router = APIRouter(prefix="/api/packing", tags=["packing"])


def _get_list(db: Session, list_id: int) -> PackingList:
    packing_list = db.get(PackingList, list_id)
    if packing_list is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "List not found")
    return packing_list


def _get_section(db: Session, section_id: int) -> PackingSection:
    section = db.get(PackingSection, section_id)
    if section is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Section not found")
    return section


def _get_item(db: Session, item_id: int) -> PackingItem:
    item = db.get(PackingItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    return item


def _detail(db: Session, packing_list: PackingList) -> PackingListDetail:
    return list_to_detail(
        packing_list, packing_service.reminder_enabled(db, packing_list)
    )


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

@router.get("/templates", response_model=list[PackingListRead])
def list_templates(
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> list[PackingListRead]:
    """The ten starter templates, seeded on first call (idempotent —
    re-calling never duplicates or overwrites her edits)."""
    packing_service.seed_templates(db)
    db.commit()
    templates = db.scalars(
        select(PackingList).where(PackingList.is_template.is_(True))
    ).all()
    order = {category: index for index, category in enumerate(PACKING_CATEGORIES)}
    reads = [list_to_read(template) for template in templates]
    reads.sort(key=lambda t: order.get(t.category, len(order)))
    return reads


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------

@router.get("/lists", response_model=list[PackingListRead])
def list_lists(
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> list[PackingListRead]:
    """Every real (non-template) list, newest first — the index splits
    active from archived client-side."""
    lists = db.scalars(
        select(PackingList)
        .where(PackingList.is_template.is_(False))
        .order_by(PackingList.created_at.desc())
    ).all()
    return [list_to_read(packing_list) for packing_list in lists]


@router.post("/lists", response_model=PackingListDetail, status_code=status.HTTP_201_CREATED)
def create_list(
    payload: PackingListCreate,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> PackingListDetail:
    """Clone a source list into a fresh active one. The source can be a
    starter template ("new from template") or an archived list ("reuse")
    — templates are just template-flagged lists, so it's the same clone."""
    source = _get_list(db, payload.source_list_id)
    name = (payload.name or source.name).strip()
    new_list = packing_service.clone_list(db, source, name, payload.event_date)
    db.commit()
    db.refresh(new_list)
    return _detail(db, new_list)


@router.get("/lists/{list_id}", response_model=PackingListDetail)
def get_list(
    list_id: int,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> PackingListDetail:
    return _detail(db, _get_list(db, list_id))


@router.patch("/lists/{list_id}", response_model=PackingListDetail)
def update_list(
    list_id: int,
    payload: PackingListUpdate,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> PackingListDetail:
    """Rename, set/clear the event date, archive/restore, and toggle the
    countdown reminder. Archiving keeps everything (never delete a
    finished trip — it's the seed for the next one) and quiets any
    pending nudge."""
    packing_list = _get_list(db, list_id)

    if payload.name is not None:
        packing_list.name = payload.name.strip()
    if payload.clear_event_date:
        packing_list.event_date = None
    elif payload.event_date is not None:
        packing_list.event_date = payload.event_date
    if payload.status is not None:
        if packing_list.is_template:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Templates can't be archived"
            )
        packing_list.status = payload.status

    # Re-sync the reminder against the list's new state: an explicit
    # toggle wins; otherwise keep an existing nudge aligned with any
    # date/status change (archiving or clearing the date quiets it).
    if payload.reminder_enabled is not None:
        wants_reminder = payload.reminder_enabled
    else:
        wants_reminder = packing_service.reminder_enabled(db, packing_list)
    if payload.reminder_enabled and packing_list.event_date is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Set an event date to get a reminder"
        )
    packing_service.sync_countdown_reminder(
        db, current_user, packing_list, wants_reminder, payload.reminder_days_before
    )

    db.commit()
    db.refresh(packing_list)
    return _detail(db, packing_list)


@router.delete("/lists/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_list(
    list_id: int,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> None:
    """Hard delete — for lists made by mistake. Finished lists should be
    archived instead. Templates are protected."""
    packing_list = _get_list(db, list_id)
    if packing_list.is_template:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Templates can't be deleted")
    db.delete(packing_list)
    db.commit()


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

@router.post(
    "/lists/{list_id}/sections",
    response_model=PackingListDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_section(
    list_id: int,
    payload: PackingSectionCreate,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> PackingListDetail:
    packing_list = _get_list(db, list_id)
    packing_list.sections.append(
        PackingSection(
            name=payload.name.strip(), sort_order=len(packing_list.sections)
        )
    )
    db.commit()
    db.refresh(packing_list)
    return _detail(db, packing_list)


@router.patch("/sections/{section_id}", response_model=PackingListDetail)
def update_section(
    section_id: int,
    payload: PackingSectionUpdate,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> PackingListDetail:
    section = _get_section(db, section_id)
    if payload.name is not None:
        section.name = payload.name.strip()
    if payload.sort_order is not None:
        packing_service.move_section(db, section, payload.sort_order)
    db.commit()
    packing_list = _get_list(db, section.list_id)
    db.refresh(packing_list)
    return _detail(db, packing_list)


@router.delete("/sections/{section_id}", response_model=PackingListDetail)
def delete_section(
    section_id: int,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> PackingListDetail:
    section = _get_section(db, section_id)
    list_id = section.list_id
    db.delete(section)
    db.commit()
    packing_list = _get_list(db, list_id)
    db.refresh(packing_list)
    return _detail(db, packing_list)


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------

@router.post(
    "/sections/{section_id}/items",
    response_model=PackingListDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_item(
    section_id: int,
    payload: PackingItemCreate,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> PackingListDetail:
    section = _get_section(db, section_id)
    section.items.append(
        PackingItem(
            name=payload.name.strip(),
            quantity=payload.quantity,
            notes=payload.notes,
            sort_order=len(section.items),
        )
    )
    db.commit()
    packing_list = _get_list(db, section.list_id)
    db.refresh(packing_list)
    return _detail(db, packing_list)


@router.patch("/items/{item_id}", response_model=PackingListDetail)
def update_item(
    item_id: int,
    payload: PackingItemUpdate,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> PackingListDetail:
    """Edit an item — including the checkbox itself (`packed`) and its
    position (`sort_order` as a target index)."""
    item = _get_item(db, item_id)
    if payload.name is not None:
        item.name = payload.name.strip()
    if payload.clear_quantity:
        item.quantity = None
    elif payload.quantity is not None:
        item.quantity = payload.quantity
    if payload.clear_notes:
        item.notes = None
    elif payload.notes is not None:
        item.notes = payload.notes
    if payload.packed is not None:
        item.packed = payload.packed
    if payload.sort_order is not None:
        packing_service.move_item(db, item, payload.sort_order)
    db.commit()
    section = _get_section(db, item.section_id)
    packing_list = _get_list(db, section.list_id)
    db.refresh(packing_list)
    return _detail(db, packing_list)


@router.delete("/items/{item_id}", response_model=PackingListDetail)
def delete_item(
    item_id: int,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> PackingListDetail:
    item = _get_item(db, item_id)
    section = _get_section(db, item.section_id)
    list_id = section.list_id
    db.delete(item)
    db.commit()
    packing_list = _get_list(db, list_id)
    db.refresh(packing_list)
    return _detail(db, packing_list)
