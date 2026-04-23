"""add_struct_layer_tables

Revision ID: a28d933a0fab
Revises: a3df65cc10b1
Create Date: 2026-04-23 09:21:31.090011
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a28d933a0fab'
down_revision: Union[str, None] = 'a3df65cc10b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. struct_style_bucket
    op.create_table(
        'struct_style_bucket',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('centroid_embedding', sa.LargeBinary(), nullable=False),
        sa.Column('member_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('enricher_version', sa.String(), nullable=False),
        sa.Column('active', sa.Boolean(), server_default='1', nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    # 2. struct_clip_tags
    op.create_table(
        'struct_clip_tags',
        sa.Column('scene_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('role_confidence', sa.Float(), nullable=False),
        sa.Column('mood_refined', sa.String(), nullable=False),
        sa.Column('mood_confidence', sa.Float(), nullable=False),
        sa.Column('style_bucket_id', sa.Integer(), nullable=False),
        sa.Column('style_distance', sa.Float(), nullable=False),
        sa.Column('enriched_at', sa.DateTime(), nullable=False),
        sa.Column('enricher_version', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['scene_id'], ['scenes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['style_bucket_id'], ['struct_style_bucket.id'], ),
        sa.PrimaryKeyConstraint('scene_id')
    )
    op.create_index('idx_struct_clip_tags_role', 'struct_clip_tags', ['role'], unique=False)
    op.create_index('idx_struct_clip_tags_mood', 'struct_clip_tags', ['mood_refined'], unique=False)
    op.create_index('idx_struct_clip_tags_style', 'struct_clip_tags', ['style_bucket_id'], unique=False)

    # 3. struct_compat_edge
    op.create_table(
        'struct_compat_edge',
        sa.Column('scene_id_a', sa.Integer(), nullable=False),
        sa.Column('scene_id_b', sa.Integer(), nullable=False),
        sa.Column('cosine_similarity', sa.Float(), nullable=False),
        sa.Column('rank_in_a', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['scene_id_a'], ['scenes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['scene_id_b'], ['scenes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('scene_id_a', 'scene_id_b')
    )
    op.create_index('idx_struct_compat_edge_a_rank', 'struct_compat_edge', ['scene_id_a', 'rank_in_a'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_struct_compat_edge_a_rank', table_name='struct_compat_edge')
    op.drop_table('struct_compat_edge')
    op.drop_index('idx_struct_clip_tags_style', table_name='struct_clip_tags')
    op.drop_index('idx_struct_clip_tags_mood', table_name='struct_clip_tags')
    op.drop_index('idx_struct_clip_tags_role', table_name='struct_clip_tags')
    op.drop_table('struct_clip_tags')
    op.drop_table('struct_style_bucket')
