"""Add bundled exercise catalog.

Revision ID: 323eb234b9c0
Revises: 82ab19d34f60
"""

import sqlalchemy as sa
from sqlmodel.sql.sqltypes import AutoString

from alembic import op

revision: str = "323eb234b9c0"
down_revision: str | None = "82ab19d34f60"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create the catalog tables."""
    op.create_table(
        "exercise_catalog_sync_state",
        sa.Column("catalog_code", AutoString(), nullable=False),
        sa.Column("content_hash", AutoString(), nullable=False),
        sa.Column("sync_version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "btrim(catalog_code) <> ''", name="ck_catalog_sync_code_not_empty"
        ),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'", name="ck_catalog_sync_hash"
        ),
        sa.CheckConstraint("sync_version > 0", name="ck_catalog_sync_version_positive"),
        sa.PrimaryKeyConstraint("catalog_code"),
    )
    op.create_table(
        "exercises",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", AutoString(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("btrim(code) <> ''", name="ck_exercises_code_not_empty"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uix_exercises_code"),
    )
    op.create_table(
        "muscle_groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", AutoString(), nullable=False),
        sa.CheckConstraint("btrim(code) <> ''", name="ck_muscle_groups_code_not_empty"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uix_muscle_groups_code"),
    )
    op.create_table(
        "muscles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", AutoString(), nullable=False),
        sa.CheckConstraint("btrim(code) <> ''", name="ck_muscles_code_not_empty"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uix_muscles_code"),
    )
    op.create_table(
        "exercise_muscles",
        sa.Column("exercise_id", sa.Uuid(), nullable=False),
        sa.Column("muscle_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("PRIMARY", "SECONDARY", name="exercisemusclerole"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["muscle_id"], ["muscles.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("exercise_id", "muscle_id"),
    )
    op.create_table(
        "muscle_group_members",
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("muscle_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["group_id"], ["muscle_groups.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["muscle_id"], ["muscles.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("group_id", "muscle_id"),
    )


def downgrade() -> None:
    """Remove the catalog tables."""
    op.drop_table("muscle_group_members")
    op.drop_table("exercise_muscles")
    op.drop_table("muscles")
    op.drop_table("muscle_groups")
    op.drop_table("exercises")
    op.drop_table("exercise_catalog_sync_state")
    sa.Enum(name="exercisemusclerole").drop(op.get_bind())
