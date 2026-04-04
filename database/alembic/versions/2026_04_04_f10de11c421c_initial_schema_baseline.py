"""initial schema baseline

Revision ID: f10de11c421c
Revises:
Create Date: 2026-04-04 14:44:49.913702

This is a baseline migration representing the full PB Studio schema.
On fresh databases it creates all tables; on existing databases it is
stamped as already applied via init_db().
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f10de11c421c'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- projects --
    op.create_table(
        'projects',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('path', sa.String(), nullable=False),
        sa.Column('resolution', sa.String(), nullable=False, server_default='1920x1080'),
        sa.Column('fps', sa.Float(), nullable=False, server_default='30.0'),
    )

    # -- audio_tracks --
    op.create_table(
        'audio_tracks',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('file_path', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('duration', sa.Float(), nullable=True),
        sa.Column('sample_rate', sa.Integer(), nullable=True, server_default='44100'),
        sa.Column('bpm', sa.Float(), nullable=True),
        sa.Column('key', sa.String(), nullable=True),
        sa.Column('energy_curve', sa.Text(), nullable=True),
        sa.Column('stem_vocals_path', sa.String(), nullable=True),
        sa.Column('stem_drums_path', sa.String(), nullable=True),
        sa.Column('stem_bass_path', sa.String(), nullable=True),
        sa.Column('stem_other_path', sa.String(), nullable=True),
        sa.Column('key_confidence', sa.Float(), nullable=True),
        sa.Column('lufs', sa.Float(), nullable=True),
        sa.Column('mood', sa.String(), nullable=True),
        sa.Column('genre', sa.String(), nullable=True),
        sa.Column('is_dj_mix', sa.Boolean(), nullable=True, server_default='0'),
        sa.Column('spectral_bands', sa.Text(), nullable=True),
        sa.Column('key_modulation_data', sa.Text(), nullable=True),
        sa.Column('harmonic_tension_curve', sa.Text(), nullable=True),
        sa.UniqueConstraint('project_id', 'file_path', name='uq_audio_tracks_project_file'),
    )
    op.create_index('ix_audio_tracks_project_id', 'audio_tracks', ['project_id'])

    # -- video_clips --
    op.create_table(
        'video_clips',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('file_path', sa.String(), nullable=False),
        sa.Column('proxy_path', sa.String(), nullable=True),
        sa.Column('duration', sa.Float(), nullable=True),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('fps', sa.Float(), nullable=True),
        sa.Column('codec', sa.String(), nullable=True),
        sa.UniqueConstraint('project_id', 'file_path', name='uq_video_clips_project_file'),
    )
    op.create_index('ix_video_clips_project_id', 'video_clips', ['project_id'])

    # -- scenes --
    op.create_table(
        'scenes',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('video_clip_id', sa.Integer(), sa.ForeignKey('video_clips.id', ondelete='CASCADE'), nullable=False),
        sa.Column('start_time', sa.Float(), nullable=False),
        sa.Column('end_time', sa.Float(), nullable=False),
        sa.Column('label', sa.String(), nullable=True),
        sa.Column('energy', sa.Float(), nullable=True),
    )
    op.create_index('ix_scenes_video_clip_id', 'scenes', ['video_clip_id'])

    # -- beatgrids --
    op.create_table(
        'beatgrids',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('audio_track_id', sa.Integer(), sa.ForeignKey('audio_tracks.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('bpm', sa.Float(), nullable=False),
        sa.Column('offset', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('beat_positions', sa.Text(), nullable=True),
        sa.Column('downbeat_positions', sa.Text(), nullable=True),
        sa.Column('energy_per_beat', sa.Text(), nullable=True),
        sa.Column('onset_kick_data', sa.Text(), nullable=True),
        sa.Column('onset_snare_data', sa.Text(), nullable=True),
        sa.Column('onset_hihat_data', sa.Text(), nullable=True),
        sa.Column('syncopation_score', sa.Float(), nullable=True),
        sa.Column('groove_template', sa.Text(), nullable=True),
    )
    op.create_index('ix_beatgrids_audio_track_id', 'beatgrids', ['audio_track_id'])

    # -- waveform_data --
    op.create_table(
        'waveform_data',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('audio_track_id', sa.Integer(), sa.ForeignKey('audio_tracks.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('num_samples', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('duration', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('band_low', sa.Text(), nullable=False),
        sa.Column('band_mid', sa.Text(), nullable=False),
        sa.Column('band_high', sa.Text(), nullable=False),
    )
    op.create_index('ix_waveform_data_audio_track_id', 'waveform_data', ['audio_track_id'])

    # -- pacing_blueprints --
    op.create_table(
        'pacing_blueprints',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('style', sa.String(), nullable=True),
        sa.Column('cuts_per_bar', sa.Integer(), nullable=True, server_default='1'),
        sa.Column('energy_curve', sa.Text(), nullable=True),
    )

    # -- audio_video_anchors --
    op.create_table(
        'audio_video_anchors',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('audio_track_id', sa.Integer(), sa.ForeignKey('audio_tracks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('video_clip_id', sa.Integer(), sa.ForeignKey('video_clips.id', ondelete='CASCADE'), nullable=False),
        sa.Column('audio_time', sa.Float(), nullable=False),
        sa.Column('video_time', sa.Float(), nullable=False),
        sa.Column('anchor_type', sa.String(), nullable=True, server_default='beat'),
    )
    op.create_index('ix_audio_video_anchors_audio_track_id', 'audio_video_anchors', ['audio_track_id'])
    op.create_index('ix_audio_video_anchors_video_clip_id', 'audio_video_anchors', ['video_clip_id'])

    # -- timeline_entries --
    op.create_table(
        'timeline_entries',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('track', sa.String(), nullable=False),
        sa.Column('media_id', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('end_time', sa.Float(), nullable=True),
        sa.Column('lane', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('crossfade_duration', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('source_start', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('source_end', sa.Float(), nullable=True),
        sa.Column('brightness', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('contrast', sa.Float(), nullable=True, server_default='1.0'),
    )
    op.create_index('ix_timeline_entries_project_id', 'timeline_entries', ['project_id'])

    # -- clip_anchors --
    op.create_table(
        'clip_anchors',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('timeline_entry_id', sa.Integer(), sa.ForeignKey('timeline_entries.id', ondelete='CASCADE'), nullable=False),
        sa.Column('time_offset', sa.Float(), nullable=False),
        sa.Column('label', sa.String(), nullable=True, server_default=''),
        sa.Column('color', sa.String(), nullable=True, server_default='#FF3333'),
    )
    op.create_index('ix_clip_anchors_timeline_entry_id', 'clip_anchors', ['timeline_entry_id'])

    # -- ai_pacing_memory --
    op.create_table(
        'ai_pacing_memory',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('created_at', sa.String(), nullable=True),
        sa.Column('bpm', sa.Float(), nullable=True),
        sa.Column('bass_energy', sa.Float(), nullable=True),
        sa.Column('drum_energy', sa.Float(), nullable=True),
        sa.Column('overall_energy', sa.Float(), nullable=True),
        sa.Column('mood', sa.String(), nullable=True),
        sa.Column('audio_time', sa.Float(), nullable=True),
        sa.Column('raft_motion', sa.Float(), nullable=True),
        sa.Column('siglip_tags', sa.Text(), nullable=True),
        sa.Column('cut_type', sa.String(), nullable=True),
        sa.Column('crossfade_duration', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('section_type', sa.String(), nullable=True),
        sa.Column('scene_id', sa.Integer(), sa.ForeignKey('scenes.id', ondelete='SET NULL'), nullable=True),
        sa.Column('audio_track_id', sa.Integer(), sa.ForeignKey('audio_tracks.id', ondelete='CASCADE'), nullable=True),
        sa.Column('label', sa.String(), nullable=True),
    )
    op.create_index('ix_ai_pacing_memory_audio_track_id', 'ai_pacing_memory', ['audio_track_id'])

    # -- structure_segments --
    op.create_table(
        'structure_segments',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('audio_track_id', sa.Integer(), sa.ForeignKey('audio_tracks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('start_time', sa.Float(), nullable=False),
        sa.Column('end_time', sa.Float(), nullable=False),
        sa.Column('label', sa.String(), nullable=False),
        sa.Column('energy', sa.Float(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
    )
    op.create_index('ix_structure_segments_audio_track_id', 'structure_segments', ['audio_track_id'])

    # -- hotcues --
    op.create_table(
        'hotcues',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('audio_track_id', sa.Integer(), sa.ForeignKey('audio_tracks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('time', sa.Float(), nullable=False),
        sa.Column('label', sa.String(), nullable=True, server_default=''),
        sa.Column('color', sa.String(), nullable=True, server_default='#FF3333'),
        sa.Column('cue_type', sa.String(), nullable=True, server_default='cue'),
    )
    op.create_index('ix_hotcues_audio_track_id', 'hotcues', ['audio_track_id'])

    # -- model_registry --
    op.create_table(
        'model_registry',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('model_id', sa.String(), nullable=False, unique=True),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('display_name', sa.String(), nullable=True),
        sa.Column('size_mb', sa.Float(), nullable=True),
        sa.Column('installed_at', sa.String(), nullable=True),
        sa.Column('last_used_at', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='installed'),
        sa.Column('local_path', sa.String(), nullable=True),
        sa.Column('metadata_json', sa.Text(), nullable=True),
    )
    op.create_index('ix_model_registry_source', 'model_registry', ['source'])
    op.create_index('ix_model_registry_last_used', 'model_registry', ['last_used_at'])

    # -- agent_feedback --
    op.create_table(
        'agent_feedback',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('created_at', sa.String(), nullable=True),
        sa.Column('session_id', sa.String(), nullable=True),
        sa.Column('model_id', sa.String(), nullable=True),
        sa.Column('backend', sa.String(), nullable=True, server_default='ollama'),
        sa.Column('user_query', sa.Text(), nullable=False),
        sa.Column('ai_response', sa.Text(), nullable=False),
        sa.Column('action_name', sa.String(), nullable=True),
        sa.Column('rating', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('user_comment', sa.Text(), nullable=True),
    )
    op.create_index('ix_agent_feedback_rating', 'agent_feedback', ['rating'])
    op.create_index('ix_agent_feedback_action', 'agent_feedback', ['action_name'])

    # -- style_presets --
    op.create_table(
        'style_presets',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(), nullable=False, unique=True),
        sa.Column('cut_rate', sa.Float(), nullable=True, server_default='1.0'),
        sa.Column('energy_reactivity', sa.Float(), nullable=True, server_default='0.7'),
        sa.Column('breakdown_behavior', sa.String(), nullable=True, server_default='halve'),
        sa.Column('min_clip_duration', sa.Float(), nullable=True, server_default='1.0'),
        sa.Column('max_clip_duration', sa.Float(), nullable=True, server_default='8.0'),
        sa.Column('beat_weight', sa.Float(), nullable=True, server_default='1.0'),
        sa.Column('kick_weight', sa.Float(), nullable=True, server_default='1.0'),
        sa.Column('snare_weight', sa.Float(), nullable=True, server_default='0.8'),
        sa.Column('hihat_weight', sa.Float(), nullable=True, server_default='0.3'),
        sa.Column('description', sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('style_presets')
    op.drop_table('agent_feedback')
    op.drop_table('model_registry')
    op.drop_table('hotcues')
    op.drop_table('structure_segments')
    op.drop_table('ai_pacing_memory')
    op.drop_table('clip_anchors')
    op.drop_table('timeline_entries')
    op.drop_table('audio_video_anchors')
    op.drop_table('pacing_blueprints')
    op.drop_table('waveform_data')
    op.drop_table('beatgrids')
    op.drop_table('scenes')
    op.drop_table('video_clips')
    op.drop_table('audio_tracks')
    op.drop_table('projects')
