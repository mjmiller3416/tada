"""oauth tables for the ChatGPT MCP connector

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-14

Additive only (SPEC §8): three new tables backing the OAuth 2.1
authorization server ChatGPT signs in through (routers/oauth.py) —
registered clients, single-use authorization codes, and access/refresh
tokens. Every secret is stored as a SHA-256 hash; nothing existing is
touched, so the downgrade just drops the three tables.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "oauth_clients",
        sa.Column("client_id", sa.String(64), primary_key=True),
        sa.Column("secret_hash", sa.String(64), nullable=True),
        sa.Column("client_name", sa.String(200), nullable=True),
        sa.Column("redirect_uris", sa.Text(), nullable=False),
        sa.Column("token_endpoint_auth_method", sa.String(40), nullable=False),
        sa.Column("grant_types", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "oauth_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "client_id",
            sa.String(64),
            sa.ForeignKey("oauth_clients.client_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("code_challenge", sa.String(128), nullable=False),
        sa.Column("resource", sa.Text(), nullable=True),
        sa.Column("scope", sa.String(100), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "oauth_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column(
            "client_id",
            sa.String(64),
            sa.ForeignKey("oauth_clients.client_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "code_id",
            sa.Integer(),
            sa.ForeignKey("oauth_codes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("scope", sa.String(100), nullable=False),
        sa.Column("resource", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_oauth_tokens_user_id", "oauth_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_oauth_tokens_user_id", table_name="oauth_tokens")
    op.drop_table("oauth_tokens")
    op.drop_table("oauth_codes")
    op.drop_table("oauth_clients")
