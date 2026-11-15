"""Add active-day goal aggregation.

Revision ID: 82ab19d34f60
Revises: 1f6fbf03c352
"""

import sqlalchemy as sa

from alembic import op

revision = "82ab19d34f60"
down_revision = "1f6fbf03c352"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE goalaggregation ADD VALUE IF NOT EXISTS 'ACTIVE_DAYS'")


def downgrade() -> None:
    op.execute("LOCK TABLE goals IN ACCESS EXCLUSIVE MODE")
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM goals "
                "WHERE aggregation::text = 'ACTIVE_DAYS')"
            )
        )
        .scalar_one()
    ):
        raise RuntimeError("Remove active-day goals before downgrading this revision")
    op.execute("ALTER TYPE goalaggregation RENAME TO goalaggregation_with_active_days")
    op.execute(
        "CREATE TYPE goalaggregation AS ENUM "
        "('COUNT', 'TOTAL_DISTANCE', 'AVG_DISTANCE', 'MAX_DISTANCE', 'DURATION')"
    )
    op.execute(
        "ALTER TABLE goals ALTER COLUMN aggregation TYPE goalaggregation "
        "USING aggregation::text::goalaggregation"
    )
    op.execute("DROP TYPE goalaggregation_with_active_days")
