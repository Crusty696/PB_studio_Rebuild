"""add index idx_timeline_project and idx_hotcue_audio

Revision ID: 9da529c08d55
Revises: d4e5f6a7b8c9
Create Date: 2026-06-12 23:51:29.088136
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9da529c08d55'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_exists(index_name: str, table_name: str) -> bool:
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = inspector.get_indexes(table_name)
    return any(idx['name'] == index_name for idx in indexes)


def upgrade() -> None:
    if not _index_exists('idx_timeline_project', 'timeline_entries'):
        op.create_index('idx_timeline_project', 'timeline_entries', ['project_id'])
    if not _index_exists('idx_hotcue_audio', 'hotcues'):
        op.create_index('idx_hotcue_audio', 'hotcues', ['audio_track_id'])


def downgrade() -> None:
    if _index_exists('idx_timeline_project', 'timeline_entries'):
        op.drop_index('idx_timeline_project', table_name='timeline_entries')
    if _index_exists('idx_hotcue_audio', 'hotcues'):
        op.drop_index('idx_hotcue_audio', table_name='hotcues')
