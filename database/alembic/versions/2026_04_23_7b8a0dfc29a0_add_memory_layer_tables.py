"""add_memory_layer_tables

Revision ID: 7b8a0dfc29a0
Revises: a28d933a0fab
Create Date: 2026-04-23 09:21:39.213877
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7b8a0dfc29a0'
down_revision: Union[str, None] = 'a28d933a0fab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. mem_pacing_run
    op.create_table(
        'mem_pacing_run',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('audio_track_id', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('is_dj_mix', sa.Boolean(), nullable=False),
        sa.Column('total_duration_sec', sa.Float(), nullable=False),
        sa.Column('total_cuts', sa.Integer(), server_default='0', nullable=False),
        sa.Column('agent_version', sa.String(), nullable=False),
        sa.Column('weights_profile', sa.String(), nullable=False),
        sa.Column('user_rating', sa.Integer(), nullable=True),
        sa.Column('user_notes', sa.Text(), nullable=True),
        sa.Column('steer_snapshot', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['audio_track_id'], ['audio_tracks.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # 2. mem_decision
    op.create_table(
        'mem_decision',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('run_id', sa.Integer(), nullable=False),
        sa.Column('sequence_idx', sa.Integer(), nullable=False),
        sa.Column('at_timestamp_sec', sa.Float(), nullable=False),
        sa.Column('at_beat_idx', sa.Integer(), nullable=True),
        sa.Column('at_structure_segment_id', sa.Integer(), nullable=True),
        sa.Column('at_bpm', sa.Float(), nullable=True),
        sa.Column('at_energy', sa.Float(), nullable=True),
        sa.Column('at_section_type', sa.String(), nullable=True),
        sa.Column('at_key', sa.String(), nullable=True),
        sa.Column('at_key_confidence', sa.Float(), nullable=True),
        sa.Column('at_key_modulation', sa.Boolean(), nullable=True),
        sa.Column('at_harmonic_tension', sa.Float(), nullable=True),
        sa.Column('at_mood_audio', sa.String(), nullable=True),
        sa.Column('at_genre', sa.String(), nullable=True),
        sa.Column('at_sub_genre', sa.String(), nullable=True),
        sa.Column('at_spectral_hash', sa.String(), nullable=True),
        sa.Column('at_groove_template', sa.String(), nullable=True),
        sa.Column('at_lufs', sa.Float(), nullable=True),
        sa.Column('scene_id', sa.Integer(), nullable=False),
        sa.Column('clip_role', sa.String(), nullable=False),
        sa.Column('clip_mood_refined', sa.String(), nullable=False),
        sa.Column('clip_style_bucket_id', sa.Integer(), nullable=False),
        sa.Column('clip_motion_score', sa.Float(), nullable=True),
        sa.Column('agent_score', sa.Float(), nullable=False),
        sa.Column('agent_rationale', sa.JSON(), nullable=False),
        sa.Column('user_verdict', sa.String(), nullable=True),
        sa.Column('user_verdict_at', sa.DateTime(), nullable=True),
        sa.Column('user_rating', sa.Integer(), nullable=True),
        sa.Column('at_enricher_version', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['run_id'], ['mem_pacing_run.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['scene_id'], ['scenes.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_mem_decision_run', 'mem_decision', ['run_id', 'sequence_idx'], unique=False)
    op.create_index('idx_mem_decision_scene', 'mem_decision', ['scene_id'], unique=False)
    op.create_index('idx_mem_decision_verdict', 'mem_decision', ['user_verdict'], unique=False)
    op.create_index('idx_mem_decision_context_hash', 'mem_decision', ['at_genre', 'at_section_type', 'at_bpm'], unique=False)

    # 3. mem_learned_pattern
    op.create_table(
        'mem_learned_pattern',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('pattern_type', sa.String(), nullable=False),
        sa.Column('context_fingerprint', sa.JSON(), nullable=True),
        sa.Column('target_ref', sa.JSON(), nullable=True),
        sa.Column('stat_accept_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('stat_reject_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('stat_sample_size', sa.Integer(), server_default='0', nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('last_updated', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_mem_learned_pattern_type', 'mem_learned_pattern', ['pattern_type'], unique=False)

    # 4. mem_user_feedback_event
    op.create_table(
        'mem_user_feedback_event',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('decision_id', sa.Integer(), nullable=True),
        sa.Column('run_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['mem_pacing_run.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('mem_user_feedback_event')
    op.drop_index('idx_mem_learned_pattern_type', table_name='mem_learned_pattern')
    op.drop_table('mem_learned_pattern')
    op.drop_index('idx_mem_decision_context_hash', table_name='mem_decision')
    op.drop_index('idx_mem_decision_verdict', table_name='mem_decision')
    op.drop_index('idx_mem_decision_scene', table_name='mem_decision')
    op.drop_index('idx_mem_decision_run', table_name='mem_decision')
    op.drop_table('mem_decision')
    op.drop_table('mem_pacing_run')
