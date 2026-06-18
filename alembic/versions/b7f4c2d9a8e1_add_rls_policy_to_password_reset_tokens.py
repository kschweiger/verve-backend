"""Add RLS policy to password reset tokens

Revision ID: b7f4c2d9a8e1
Revises: aae45b3b144e
Create Date: 2026-06-18 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
from verve_backend.core.config import settings

# revision identifiers, used by Alembic.
revision: str = "b7f4c2d9a8e1"
down_revision: Union[str, Sequence[str], None] = "aae45b3b144e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    schema = settings.POSTGRES_SCHEMA

    op.execute(f"ALTER TABLE {schema}.password_reset_tokens ENABLE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY password_reset_token_isolation_policy
        ON {schema}.password_reset_tokens
        FOR ALL USING (user_id = current_setting('verve_user.curr_user')::uuid)
    """)


def downgrade() -> None:
    """Downgrade schema."""
    schema = settings.POSTGRES_SCHEMA

    op.execute(
        f"DROP POLICY IF EXISTS password_reset_token_isolation_policy "
        f"ON {schema}.password_reset_tokens"
    )
    op.execute(f"ALTER TABLE {schema}.password_reset_tokens DISABLE ROW LEVEL SECURITY")
