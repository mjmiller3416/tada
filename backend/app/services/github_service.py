"""One-tap in-app feedback -> a GitHub issue on the Tada repo.

No feedback table and no migration: GitHub is the only store. If the
GitHub call fails, the full submission is logged at ERROR so it's
recoverable from the Railway console instead of just vanishing.

`@claude` is stripped from the user's message before the issue is built.
claude.yml dispatches the Claude Code Action on any `issues: opened`
event whose body contains the literal string "@claude" — a stray
"maybe @claude can look at this" in her own words would fire it with no
triage. Dispatching a review stays a deliberate, manual comment from
the repo owner.
"""

import logging
import re

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

API_BASE = "https://api.github.com"
REQUEST_TIMEOUT_SECONDS = 10.0

CATEGORY_TO_LABEL: dict[str, str] = {
    "Something's broken": "bug",
    "Idea": "enhancement",
}
FALLBACK_LABEL = "feedback"

_CLAUDE_MENTION = re.compile(r"@claude", re.IGNORECASE)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

#: Caps on client-supplied metadata (issue #26): the schema allows an
#: arbitrary dict, and an oversized body 422s at GitHub — which the
#: router can only surface as a generic failure for a message that was
#: itself fine.
MAX_METADATA_ITEMS = 20
MAX_METADATA_KEY_LEN = 100
MAX_METADATA_VALUE_LEN = 500
MAX_NAME_LEN = 100


class GitHubIssueError(Exception):
    """Raised when GitHub rejects or can't be reached for a new issue."""


def _sanitize(message: str) -> str:
    """Breaks the literal `@claude` trigger string so a stray mention in
    her own words can't auto-dispatch the Action."""
    return _CLAUDE_MENTION.sub("@ claude", message)


def _clean_field(value: str, max_len: int) -> str:
    """The treatment every non-message string gets before it can reach
    the issue (issue #26): the same trigger-mention break as the message,
    control characters stripped, newlines flattened, and a length cap —
    client-supplied metadata must never be able to auto-dispatch the
    Action or oversize the body."""
    value = _sanitize(value)
    value = _CONTROL_CHARS.sub("", value)
    value = " ".join(value.split())
    return value[:max_len]


def _build_title(category: str, sanitized_message: str) -> str:
    # Flatten to one line first: a message starting with a short line +
    # newline must not become a mangled multi-line title.
    first_line = " ".join(sanitized_message.split())
    return f"[{_clean_field(category, 50)}] {first_line[:60].strip()}"


def _build_body(
    submitter_name: str,
    submitter_role: str,
    sanitized_message: str,
    metadata: dict[str, str | None] | None,
) -> str:
    name = _clean_field(submitter_name, MAX_NAME_LEN)
    role = _clean_field(submitter_role, 50)
    lines = [f"**From:** {name} ({role})", "", "---", "", sanitized_message]

    present = {k: v for k, v in (metadata or {}).items() if v is not None}
    if present:
        lines += ["", "**Context:**"]
        lines += [
            f"- **{_clean_field(key, MAX_METADATA_KEY_LEN)}:** "
            f"{_clean_field(value, MAX_METADATA_VALUE_LEN)}"
            for key, value in list(present.items())[:MAX_METADATA_ITEMS]
        ]

    return "\n".join(lines)


class GitHubService:
    """Thin wrapper around the GitHub Issues REST API for the one repo
    configured via GITHUB_REPO."""

    def __init__(self) -> None:
        self.token = settings.github_token
        self.repo = settings.github_repo

    def _is_configured(self) -> bool:
        return bool(self.token and self.repo)

    def create_issue(
        self,
        *,
        submitter_name: str,
        submitter_role: str,
        category: str,
        message: str,
        metadata: dict[str, str | None] | None = None,
    ) -> str | None:
        """POSTs a new issue to the configured repo. Returns the issue's
        html_url, or None if GITHUB_TOKEN/GITHUB_REPO aren't set — the
        feature degrades silently in local dev rather than blocking
        submission. Raises GitHubIssueError on any GitHub-side failure,
        after logging the complete submission so it survives in Railway
        logs even though it never made it to GitHub."""
        if not self._is_configured():
            logger.warning("GITHUB_TOKEN/GITHUB_REPO not configured; feedback not posted")
            return None

        sanitized = _sanitize(message)
        label = CATEGORY_TO_LABEL.get(category, FALLBACK_LABEL)

        try:
            response = httpx.post(
                f"{API_BASE}/repos/{self.repo}/issues",
                json={
                    "title": _build_title(category, sanitized),
                    "body": _build_body(submitter_name, submitter_role, sanitized, metadata),
                    "labels": [label, "user-feedback"],
                },
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            response_obj = getattr(exc, "response", None)
            status_code = response_obj.status_code if response_obj is not None else None
            text = response_obj.text if response_obj is not None else str(exc)
            logger.error("GitHub issue creation failed (status=%s): %s", status_code, text)
            logger.error(
                "Feedback submission lost to GitHub failure — "
                "name=%r role=%r category=%r message=%r metadata=%r",
                submitter_name,
                submitter_role,
                category,
                message,
                metadata,
            )
            raise GitHubIssueError("Failed to create GitHub issue") from exc

        return response.json()["html_url"]
