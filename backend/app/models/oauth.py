"""OAuth 2.1 storage for the ChatGPT connector (routers/oauth.py).

Three tables, all secrets stored only as SHA-256 hashes:

- `oauth_clients`: dynamically registered clients (RFC 7591). ChatGPT
  registers itself once per connector; clients never expire.
- `oauth_codes`: single-use authorization codes (10 minutes), bound to
  the client, redirect URI, PKCE challenge, resource and approving user.
- `oauth_tokens`: access tokens (1 hour) and refresh tokens (90 days from
  last use, rotated on every refresh). `code_id` is carried through every
  rotation so a replayed authorization code can revoke the whole family
  it produced.

Tool calls made with an access token act as `user_id` — the household
member who approved the connection on the consent page.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class OAuthClient(Base):
    __tablename__ = "oauth_clients"

    client_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    #: SHA-256 of the client secret; NULL for public clients ("none").
    secret_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: JSON array of exact redirect URIs.
    redirect_uris: Mapped[str] = mapped_column(Text, nullable=False)
    token_endpoint_auth_method: Mapped[str] = mapped_column(String(40), nullable=False)
    #: JSON array, e.g. ["authorization_code", "refresh_token"].
    grant_types: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class OAuthCode(Base):
    __tablename__ = "oauth_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    client_id: Mapped[str] = mapped_column(
        ForeignKey("oauth_clients.client_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    code_challenge: Mapped[str] = mapped_column(String(128), nullable=False)
    resource: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope: Mapped[str] = mapped_column(String(100), nullable=False, default="mcp")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    #: "access" or "refresh".
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    client_id: Mapped[str] = mapped_column(
        ForeignKey("oauth_clients.client_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: The authorization code this token family descends from.
    code_id: Mapped[int | None] = mapped_column(
        ForeignKey("oauth_codes.id", ondelete="SET NULL"), nullable=True
    )
    scope: Mapped[str] = mapped_column(String(100), nullable=False, default="mcp")
    resource: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
