"""weekly chore Monday reset (one-time backdate)

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-18

A one-time DATA migration (no schema change) paired with the weekly-chore
Monday reset in services/scheduling.chores_for_user. From here on a
weekly-cadence chore (cadence_days == 7) on the kid chore surface reappears
every Monday in the member's local week and drops out the moment it's done
that week, instead of drifting back ~3.5 days after each completion.

This backdate makes that switch clean. A weekly chore already checked off
*this* week would otherwise stay hidden until next Monday, so we move its
last_done_at back to the end of last week: it reappears now, then follows
the Monday cycle. Chores last done in a previous week already read as due
and are left untouched; never-done (NULL) chores already surface too. The
end-of-last-week value (not NULL) also keeps a claimable chore reading as
recently-done — and therefore quiet — on any adult decay surface it shares.

"weekly chore" here means exactly what the surface shows: cadence_days == 7
and either assigned to a kid or left claimable. The Monday boundary is a
LOCAL-week boundary, so it is computed in the household's timezone (the
owner's `timezone` setting, else the app default), never UTC.

Idempotent: re-running finds nothing done-this-week left to move. Downgrade
is a no-op — a decay anchor can't be meaningfully un-reset, and the
recurring behavior lives in code, not data.
"""
from datetime import datetime, timedelta, timezone
from typing import Sequence, Union
from zoneinfo import ZoneInfo

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The app's default timezone (services/settings_service.DEFAULTS["timezone"]).
DEFAULT_TZ = "America/New_York"


def _household_timezone(bind) -> ZoneInfo:
    """The owner's `timezone` setting, or the app default — the zone the
    local-week boundary must be computed in."""
    settings = sa.table(
        "settings",
        sa.column("user_id", sa.Integer),
        sa.column("key", sa.String),
        sa.column("value", sa.String),
    )
    users = sa.table("users", sa.column("id", sa.Integer), sa.column("role", sa.String))
    row = bind.execute(
        sa.select(settings.c.value)
        .select_from(settings.join(users, users.c.id == settings.c.user_id))
        .where(users.c.role == "owner", settings.c.key == "timezone")
        .order_by(users.c.id)
        .limit(1)
    ).first()
    name = row[0] if row and row[0] else DEFAULT_TZ
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo(DEFAULT_TZ)


def upgrade() -> None:
    bind = op.get_bind()
    tz = _household_timezone(bind)

    now_local = datetime.now(timezone.utc).astimezone(tz)
    midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = midnight - timedelta(days=now_local.weekday())  # Monday 00:00 local
    week_start_utc = week_start.astimezone(timezone.utc)
    # End of last week: strictly before this Monday, so the chore reads
    # "due again" on the kid surface while staying fresh (recently done)
    # on any adult decay surface it also appears on.
    backdate_to = week_start_utc - timedelta(days=1)

    tasks = sa.table(
        "tasks",
        sa.column("cadence_days", sa.Integer),
        sa.column("is_active", sa.Boolean),
        sa.column("claimable", sa.Boolean),
        sa.column("assignee_id", sa.Integer),
        sa.column("last_done_at", sa.DateTime(timezone=True)),
    )
    users = sa.table("users", sa.column("id", sa.Integer), sa.column("role", sa.String))
    kid_ids = sa.select(users.c.id).where(users.c.role == "kid").scalar_subquery()

    result = bind.execute(
        tasks.update()
        .where(
            tasks.c.cadence_days == 7,
            tasks.c.is_active.is_(True),
            tasks.c.last_done_at.isnot(None),
            tasks.c.last_done_at >= week_start_utc,
            sa.or_(
                tasks.c.assignee_id.in_(kid_ids),
                sa.and_(tasks.c.assignee_id.is_(None), tasks.c.claimable.is_(True)),
            ),
        )
        .values(last_done_at=backdate_to)
    )
    print(
        f"Weekly-chore Monday reset: backdated {result.rowcount} chore(s) "
        f"done since {week_start_utc.isoformat()} to {backdate_to.isoformat()}."
    )


def downgrade() -> None:
    # One-time backdate; the recurring reset lives in code. Nothing to undo.
    pass
