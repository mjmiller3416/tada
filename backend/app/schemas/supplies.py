from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.supply import Supply

SupplyStatus = Literal["in_stock", "low", "out"]


class SupplyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class SupplyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    status: SupplyStatus | None = None


class SupplyRead(BaseModel):
    id: int
    name: str
    status: str
    last_pushed_at: datetime | None
    task_count: int

    #: True on the response to the status change that actually pushed the
    #: item into MealGenie's list — lets the UI say "added to your
    #: shopping list ✓" only when it really happened.
    pushed_to_shopping_list: bool = False


def supply_to_read(supply: Supply, pushed: bool = False) -> SupplyRead:
    return SupplyRead(
        id=supply.id,
        name=supply.name,
        status=supply.status,
        last_pushed_at=supply.last_pushed_at,
        task_count=len(supply.tasks),
        pushed_to_shopping_list=pushed,
    )
