from pydantic import BaseModel, Field


class FeedbackCreate(BaseModel):
    category: str = Field(min_length=1, max_length=50)
    message: str = Field(min_length=10, max_length=5000)
    metadata: dict[str, str | None] | None = None


class FeedbackResponse(BaseModel):
    success: bool
    message: str
    issue_url: str | None = None
