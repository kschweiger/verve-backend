"""Backend uses timezones

Revision ID: d9e3386babd7
Revises: 0b3973dab5df
Create Date: 2026-10-07 13:17:52.760775

"""

from typing import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d9e3386babd7"
down_revision: str | Sequence[str] | None = "0b3973dab5df"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_TIMEZONE = "Europe/Berlin"
TIMESTAMP_COLUMNS = (
    ("activities", "start", False),
    ("activities", "created_at", False),
    ("activity_collections", "created_at", False),
    ("activity_collections", "updated_at", False),
    ("goals", "current_updated", True),
    ("goals", "created_at", False),
    ("locations", "created_at", False),
    ("password_reset_tokens", "expires_at", False),
    ("password_reset_tokens", "used_at", True),
    ("password_reset_tokens", "created_at", False),
    ("track_points", "time", True),
    ("zone_intervals", "created_at", False),
)


def upgrade() -> None:
    """Upgrade schema."""
    # Seed existing rows while adding NOT NULL columns. New writes use the
    # application's user default or resolved activity timezone.
    for table_name in ("user_settings", "activities"):
        op.add_column(
            table_name,
            sa.Column(
                "timezone",
                sa.String(),
                nullable=False,
                server_default=DEFAULT_TIMEZONE,
            ),
        )
        op.alter_column(table_name, "timezone", server_default=None)

    # Interpret legacy timestamps as Berlin wall times, including their date's
    # DST offset. Explicit USING clauses avoid the session's TimeZone setting.
    for table_name, column_name, nullable in TIMESTAMP_COLUMNS:
        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.DateTime(timezone=False),
            type_=sa.DateTime(timezone=True),
            existing_nullable=nullable,
            postgresql_using=f"{column_name} AT TIME ZONE '{DEFAULT_TIMEZONE}'",
        )

    op.alter_column(
        "equipment",
        "purchase_date",
        existing_type=sa.DateTime(timezone=False),
        type_=sa.Date(),
        existing_nullable=True,
        postgresql_using="purchase_date::date",
    )


def downgrade() -> None:
    """Downgrade schema."""
    # A DATE no longer has its original time of day; restore it at midnight.
    op.alter_column(
        "equipment",
        "purchase_date",
        existing_type=sa.Date(),
        type_=sa.DateTime(timezone=False),
        existing_nullable=True,
        postgresql_using="purchase_date::timestamp without time zone",
    )
    for table_name, column_name, nullable in reversed(TIMESTAMP_COLUMNS):
        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(timezone=False),
            existing_nullable=nullable,
            postgresql_using=f"{column_name} AT TIME ZONE '{DEFAULT_TIMEZONE}'",
        )

    op.drop_column("activities", "timezone")
    op.drop_column("user_settings", "timezone")
