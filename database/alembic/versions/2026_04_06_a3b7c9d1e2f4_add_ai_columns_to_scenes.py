"""add ai_caption, ai_mood, ai_tags to scenes

Revision ID: a3b7c9d1e2f4
Revises: f10de11c421c
Create Date: 2026-04-06 11:00:00.000000

AUD-131: The initial baseline migration was missing these 3 columns
that were added to the Scene model for Gemma 4 vision captioning.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3b7c9d1e2f4'
down_revision: Union[str, None] = 'f10de11c421c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: columns may already exist from legacy migration or create_all()
    conn = op.get_bind()
    result = conn.execute(sa.text("PRAGMA table_info('scenes')"))
    existing_cols = {row[1] for row in result.fetchall()}

    if 'ai_caption' not in existing_cols:
        op.add_column('scenes', sa.Column('ai_caption', sa.Text(), nullable=True))
    if 'ai_mood' not in existing_cols:
        op.add_column('scenes', sa.Column('ai_mood', sa.String(), nullable=True))
    if 'ai_tags' not in existing_cols:
        op.add_column('scenes', sa.Column('ai_tags', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('scenes', 'ai_tags')
    op.drop_column('scenes', 'ai_mood')
    op.drop_column('scenes', 'ai_caption')
