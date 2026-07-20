from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    pin: str = Field(min_length=4, max_length=12)


class CurrentUserResponse(BaseModel):
    id: int
    name: str
    role: str

    model_config = {"from_attributes": True}
