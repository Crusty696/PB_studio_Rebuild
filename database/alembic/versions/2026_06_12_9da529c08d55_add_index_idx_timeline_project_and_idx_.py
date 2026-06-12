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


def upgrade() -> None:
    op.create_index('idx_timeline_project', 'timeline_entries', ['project_id'])
    op.create_index('idx_hotcue_audio', 'hotcues', ['audio_track_id'])


def downgrade() -> None:
    op.drop_index('idx_timeline_project', table_name='timeline_entries')
    op.drop_index('idx_hotcue_audio', table_name='hotcues')
