from pydantic import BaseModel, Field


class OnboardingRoom(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    # A template key from services/starter_tasks.py (e.g. "kitchen");
    # unknown values fall back to the generic template.
    type: str = Field(min_length=1, max_length=50)


class OnboardingRequest(BaseModel):
    rooms: list[OnboardingRoom] = Field(min_length=1)
    has_pets: bool = False
    has_kids: bool = False
    #: Phase 3: opt into the FlyLady zone overlay during setup — seeds
    #: the five zones and auto-maps the new rooms (SPEC §6).
    enable_zones: bool = False


class OnboardingResponse(BaseModel):
    rooms_created: int
    tasks_created: int
