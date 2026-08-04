"""POST /api/feedback — one-tap in-app feedback -> a GitHub issue.

No feedback table: GitHub is the only store (services/github_service.py
has the reasoning). A GitHub-side failure surfaces to the caller as a
generic 502 — the full submission is already logged by then, so nothing
is actually lost.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.feedback import FeedbackCreate, FeedbackResponse
from app.services.github_service import GitHubIssueError, GitHubService

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackResponse)
def submit_feedback(
    payload: FeedbackCreate,
    current_user: User = Depends(get_current_user),
) -> FeedbackResponse:
    try:
        issue_url = GitHubService().create_issue(
            submitter_name=current_user.name,
            submitter_role=current_user.role,
            category=payload.category,
            message=payload.message,
            metadata=payload.metadata,
        )
    except GitHubIssueError:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Couldn't send that just now — try again in a bit.",
        )

    return FeedbackResponse(success=True, message="Got it — thanks!", issue_url=issue_url)
