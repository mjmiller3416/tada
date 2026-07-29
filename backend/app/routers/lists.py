"""Lists routes (Phase 6, formerly /api/packing) — everything lives
under /api/lists, in its own module, so the cleaning core can't be
destabilized from here. List items never feed the focus surfaces.

Owner-only: the kids' logins don't touch lists. Mutations on
sections/items return the full list detail — lists are small, and one
canonical payload keeps the checklist UI trivially in sync.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.lists import List, ListItem, ListSection
from app.models.user import User
from app.routers.auth import require_owner
from app.schemas.lists import (
    ListCreate,
    ListDetail,
    ListItemCreate,
    ListItemUpdate,
    ListRead,
    ListSectionCreate,
    ListSectionUpdate,
    ListUpdate,
    list_to_detail,
    list_to_read,
)
from app.services import lists as list_service

router = APIRouter(prefix="/api/lists", tags=["lists"])


def _get_list(db: Session, list_id: int) -> List:
    parent_list = db.get(List, list_id)
    if parent_list is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "List not found")
    return parent_list


def _get_section(db: Session, section_id: int) -> ListSection:
    section = db.get(ListSection, section_id)
    if section is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Section not found")
    return section


def _get_item(db: Session, item_id: int) -> ListItem:
    item = db.get(ListItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    return item


def _detail(db: Session, parent_list: List) -> ListDetail:
    return list_to_detail(parent_list, list_service.reminder_enabled(db, parent_list))


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

@router.get("/templates", response_model=list[ListRead])
def list_templates(
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> list[ListRead]:
    """The starter templates, seeded on first call (idempotent per kind —
    re-calling never duplicates or overwrites her edits). Ordered by id,
    which is seed order: the packing ten first, then the Phase 6 set."""
    list_service.seed_templates(db)
    db.commit()
    templates = db.scalars(
        select(List).where(List.is_template.is_(True)).order_by(List.id)
    ).all()
    return [list_to_read(template) for template in templates]


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------

@router.get("", response_model=list[ListRead])
def list_lists(
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> list[ListRead]:
    """Every real (non-template) list, newest first — the index splits
    active from archived client-side."""
    lists = db.scalars(
        select(List)
        .where(List.is_template.is_(False))
        .order_by(List.created_at.desc())
    ).all()
    return [list_to_read(parent_list) for parent_list in lists]


@router.post("", response_model=ListDetail, status_code=status.HTTP_201_CREATED)
def create_list(
    payload: ListCreate,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> ListDetail:
    """Clone a source list into a fresh active one. The source can be a
    starter template ("new from template") or an archived list ("reuse")
    — templates are just template-flagged lists, so it's the same clone."""
    source = _get_list(db, payload.source_list_id)
    name = (payload.name or source.name).strip()
    destination = payload.destination.strip() if payload.destination else None
    duration = payload.duration.strip() if payload.duration else None
    new_list = list_service.clone_list(
        db, source, name, payload.event_date, destination or None, duration or None
    )
    db.commit()
    db.refresh(new_list)
    return _detail(db, new_list)


@router.get("/{list_id}", response_model=ListDetail)
def get_list(
    list_id: int,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> ListDetail:
    return _detail(db, _get_list(db, list_id))


@router.patch("/{list_id}", response_model=ListDetail)
def update_list(
    list_id: int,
    payload: ListUpdate,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> ListDetail:
    """Rename, set/clear the event date, destination, and duration,
    archive/restore, and toggle the countdown reminder. Archiving keeps
    everything (never delete a finished list — it's the seed for the
    next one) and quiets any pending nudge."""
    parent_list = _get_list(db, list_id)

    if payload.name is not None:
        parent_list.name = payload.name.strip()
    if payload.clear_event_date:
        parent_list.event_date = None
    elif payload.event_date is not None:
        parent_list.event_date = payload.event_date
    if payload.clear_destination:
        parent_list.destination = None
    elif payload.destination is not None:
        parent_list.destination = payload.destination.strip() or None
    if payload.clear_duration:
        parent_list.duration = None
    elif payload.duration is not None:
        parent_list.duration = payload.duration.strip() or None
    if payload.status is not None:
        if parent_list.is_template:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Templates can't be archived"
            )
        parent_list.status = payload.status

    # Re-sync the reminder against the list's new state: an explicit
    # toggle wins; otherwise keep an existing nudge aligned with any
    # date/status change (archiving or clearing the date quiets it).
    if payload.reminder_enabled is not None:
        wants_reminder = payload.reminder_enabled
    else:
        wants_reminder = list_service.reminder_enabled(db, parent_list)
    if payload.reminder_enabled and parent_list.event_date is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Set an event date to get a reminder"
        )
    list_service.sync_countdown_reminder(
        db, current_user, parent_list, wants_reminder, payload.reminder_days_before
    )

    db.commit()
    db.refresh(parent_list)
    return _detail(db, parent_list)


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_list(
    list_id: int,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> None:
    """Hard delete — for lists made by mistake. Finished lists should be
    archived instead. Templates are protected."""
    parent_list = _get_list(db, list_id)
    if parent_list.is_template:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Templates can't be deleted")
    db.delete(parent_list)
    db.commit()


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

@router.post(
    "/{list_id}/sections",
    response_model=ListDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_section(
    list_id: int,
    payload: ListSectionCreate,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> ListDetail:
    parent_list = _get_list(db, list_id)
    parent_list.sections.append(
        ListSection(name=payload.name.strip(), sort_order=len(parent_list.sections))
    )
    db.commit()
    db.refresh(parent_list)
    return _detail(db, parent_list)


@router.patch("/sections/{section_id}", response_model=ListDetail)
def update_section(
    section_id: int,
    payload: ListSectionUpdate,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> ListDetail:
    section = _get_section(db, section_id)
    if payload.name is not None:
        section.name = payload.name.strip()
    if payload.sort_order is not None:
        list_service.move_section(db, section, payload.sort_order)
    db.commit()
    parent_list = _get_list(db, section.list_id)
    db.refresh(parent_list)
    return _detail(db, parent_list)


@router.delete("/sections/{section_id}", response_model=ListDetail)
def delete_section(
    section_id: int,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> ListDetail:
    section = _get_section(db, section_id)
    list_id = section.list_id
    db.delete(section)
    db.commit()
    parent_list = _get_list(db, list_id)
    db.refresh(parent_list)
    return _detail(db, parent_list)


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------

@router.post(
    "/sections/{section_id}/items",
    response_model=ListDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_item(
    section_id: int,
    payload: ListItemCreate,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> ListDetail:
    section = _get_section(db, section_id)
    section.items.append(
        ListItem(
            name=payload.name.strip(),
            quantity=payload.quantity,
            notes=payload.notes,
            price=payload.price,
            sort_order=len(section.items),
        )
    )
    db.commit()
    parent_list = _get_list(db, section.list_id)
    db.refresh(parent_list)
    return _detail(db, parent_list)


@router.patch("/items/{item_id}", response_model=ListDetail)
def update_item(
    item_id: int,
    payload: ListItemUpdate,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> ListDetail:
    """Edit an item — including the checkbox itself (`packed`), the
    optional price, and its position (`sort_order` as a target index)."""
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
    if payload.clear_price:
        item.price = None
    elif payload.price is not None:
        item.price = payload.price
    if payload.sort_order is not None:
        list_service.move_item(db, item, payload.sort_order)
    db.commit()
    section = _get_section(db, item.section_id)
    parent_list = _get_list(db, section.list_id)
    db.refresh(parent_list)
    return _detail(db, parent_list)


@router.delete("/items/{item_id}", response_model=ListDetail)
def delete_item(
    item_id: int,
    _: User = Depends(require_owner),
    db: Session = Depends(get_db),
) -> ListDetail:
    item = _get_item(db, item_id)
    section = _get_section(db, item.section_id)
    list_id = section.list_id
    db.delete(item)
    db.commit()
    parent_list = _get_list(db, list_id)
    db.refresh(parent_list)
    return _detail(db, parent_list)
