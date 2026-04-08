"""add stem_weighted_energy to beatgrids

Revision ID: b4e8d2f3a1c5
Revises: a3b7c9d1e2f4
Create Date: 2026-04-07 02:08:00.000000

F-004: Add stem_weighted_energy column to beatgrids table for storing
PhD algorithm stem-weighted energy calculation results.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4e8d2f3a1c5'
down_revision: Union[str, None] = 'a3b7c9d1e2f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: column may already exist from create_all()
    conn = op.get_bind()
    result = conn.execute(sa.text("PRAGMA table_info('beatgrids')"))
    existing_cols = {row[1] for row in result.fetchall()}

    if 'stem_weighted_energy' not in existing_cols:
        op.add_column('beatgrids', sa.Column('stem_weighted_energy', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('beatgrids', 'stem_weighted_energy')
