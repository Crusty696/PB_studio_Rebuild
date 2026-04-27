"""add_analysis_status_table

Revision ID: da8d942ad38a
Revises: beb242bcd1fb
Create Date: 2026-04-10 02:37:02.749603
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'da8d942ad38a'
down_revision: Union[str, None] = 'beb242bcd1fb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add analysis_status table for tracking data analysis progress (VAD-36).

    B-091 Fix: Idempotent gemacht — pruef Tabellen-Existenz vor create_table.
    Verhindert Crash auf Fresh-DB die per create_all() bereits hat.
    """
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'analysis_status' not in insp.get_table_names():
        op.create_table(
            'analysis_status',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('media_type', sa.String(), nullable=False),
            sa.Column('media_id', sa.Integer(), nullable=False),
            sa.Column('step_key', sa.String(), nullable=False),
            sa.Column('status', sa.String(), nullable=False),
            sa.Column('value_summary', sa.JSON(), nullable=True),
            sa.Column('started_at', sa.DateTime(), nullable=True),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('media_type', 'media_id', 'step_key', name='uq_analysis_status_media_step')
        )
    existing_indexes = {ix['name'] for ix in insp.get_indexes('analysis_status')} if 'analysis_status' in insp.get_table_names() else set()
    if 'idx_analysis_media' not in existing_indexes:
        with op.batch_alter_table('analysis_status', schema=None) as batch_op:
            batch_op.create_index('idx_analysis_media', ['media_type', 'media_id'], unique=False)


def downgrade() -> None:
    """Remove analysis_status table."""
    with op.batch_alter_table('analysis_status', schema=None) as batch_op:
        batch_op.drop_index('idx_analysis_media')
    op.drop_table('analysis_status')
