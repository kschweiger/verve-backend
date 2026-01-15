"""Add energy column to activity and make geometry and geography optional in
track_points

Revision ID: f385499f76d8
Revises: f30aeaa82971
Create Date: 2026-01-15 21:13:08.570399

"""

from typing import Sequence, Union

import sqlalchemy as sa
from geoalchemy2 import Geography, Geometry

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f385499f76d8"
down_revision: Union[str, Sequence[str], None] = "f30aeaa82971"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("activities", sa.Column("energy", sa.Float(), nullable=True))
    op.alter_column(
        "track_points",
        "geography",
        existing_type=Geography(geometry_type="POINT", srid=4326),
        nullable=True,
    )
    op.alter_column(
        "track_points",
        "geometry",
        existing_type=Geometry(geometry_type="POINT"),
        nullable=True,
    )

    op.drop_index(
        "idx_track_points_geography", table_name="track_points", postgresql_using="gist"
    )
    op.drop_index(
        "idx_track_points_geometry", table_name="track_points", postgresql_using="gist"
    )
    # Create new Partial indices (WHERE ... IS NOT NULL)
    op.create_index(
        "idx_track_points_geography",
        "track_points",
        ["geography"],
        postgresql_using="gist",
        postgresql_where=sa.text("geography IS NOT NULL"),
    )
    op.create_index(
        "idx_track_points_geometry",
        "track_points",
        ["geometry"],
        postgresql_using="gist",
        postgresql_where=sa.text("geometry IS NOT NULL"),
    )
    bind = op.get_bind()

    # Use raw SQL to avoid dependency on model classes
    # 1. Find 'Foot Sports' ID
    res = bind.execute(
        sa.text("SELECT id FROM activity_type WHERE name = 'Foot Sports'")
    )
    foot_sports_id = res.scalar()

    if foot_sports_id is not None:
        # 2. Insert 'Walk' safely (do nothing if it exists)
        # Note: We assume the 'sub_activity_type' table exists and has the
        # UniqueConstraint
        bind.execute(
            sa.text(
                """
            INSERT INTO sub_activity_type (name, type_id)
            VALUES ('Walk', :type_id)
            ON CONFLICT (name, type_id) DO NOTHING
            """
            ),
            {"type_id": foot_sports_id},
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "idx_track_points_geography", table_name="track_points", postgresql_using="gist"
    )
    op.drop_index(
        "idx_track_points_geometry", table_name="track_points", postgresql_using="gist"
    )

    op.create_index(
        "idx_track_points_geography",
        "track_points",
        ["geography"],
        postgresql_using="gist",
    )
    op.create_index(
        "idx_track_points_geometry",
        "track_points",
        ["geometry"],
        postgresql_using="gist",
    )

    op.alter_column(
        "track_points",
        "geography",
        existing_type=Geography(geometry_type="POINT", srid=4326),
        nullable=False,
    )
    op.alter_column(
        "track_points",
        "geometry",
        existing_type=Geometry(geometry_type="POINT"),
        nullable=False,
    )

    op.drop_column("activities", "energy")
