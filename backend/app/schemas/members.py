from pydantic import BaseModel, Field


class MemberCreate(BaseModel):
    """A new kid account: just a name and a PIN (no email — kids log in
    with the PIN alone, on the same login screen as the owner)."""

    name: str = Field(min_length=1, max_length=100)
    pin: str = Field(min_length=4, max_length=12, pattern=r"^\d+$")


class MemberUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    pin: str | None = Field(default=None, min_length=4, max_length=12, pattern=r"^\d+$")


class MemberRead(BaseModel):
    id: int
    name: str
    role: str
    #: Active tasks currently assigned to this member — shown next to each
    #: kid in the household settings so she can see who has what.
    assigned_count: int
