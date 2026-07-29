from typing import Literal

from pydantic import BaseModel, Field


class MemberCreate(BaseModel):
    """A new household login: a name and a PIN (no email — everyone logs
    in with the PIN alone, on the same login screen). Kids get the
    deliberately small chores surface; a second adult (role "owner",
    Phase 4.6) sees and can change everything, exactly like her."""

    name: str = Field(min_length=1, max_length=100)
    pin: str = Field(min_length=4, max_length=12, pattern=r"^\d+$")
    role: Literal["kid", "owner"] = "kid"


class MemberUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    pin: str | None = Field(default=None, min_length=4, max_length=12, pattern=r"^\d+$")


class MemberRead(BaseModel):
    id: int
    name: str
    role: str
    #: Active tasks currently assigned to this member — shown next to each
    #: member in the household settings so she can see who has what.
    assigned_count: int
