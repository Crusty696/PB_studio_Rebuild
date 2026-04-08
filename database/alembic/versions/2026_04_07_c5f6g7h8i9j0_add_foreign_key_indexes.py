"""add foreign key indexes

Revision ID: c5f6g7h8i9j0
Revises: b4e8d2f3a1c5
Create Date: 2026-04-07 02:00:00.000000

P1-FIX: Fügt Indizes für alle Foreign Key Spalten hinzu, um Joins und
CASCADE Deletes zu beschleunigen. Behebt N+1 Query Performance-Probleme.
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'c5f6g7h8i9j0'
down_revision = 'b4e8d2f3a1c5'
branch_labels = None
depends_on = None


def upgrade():
    """Fügt Indizes für Foreign Keys hinzu."""
    # AudioTrack Foreign Keys
    op.create_index('ix_audio_tracks_project_id', 'audio_tracks', ['project_id'])

    # VideoClip Foreign Keys
    op.create_index('ix_video_clips_project_id', 'video_clips', ['project_id'])

    # Scene Foreign Keys
    op.create_index('ix_scenes_video_clip_id', 'scenes', ['video_clip_id'])

    # Beatgrid Foreign Keys
    op.create_index('ix_beatgrids_audio_track_id', 'beatgrids', ['audio_track_id'])

    # WaveformData Foreign Keys
    op.create_index('ix_waveform_data_audio_track_id', 'waveform_data', ['audio_track_id'])

    # PacingBlueprint Foreign Keys
    op.create_index('ix_pacing_blueprints_project_id', 'pacing_blueprints', ['project_id'])

    # AudioVideoAnchor Foreign Keys
    op.create_index('ix_audio_video_anchors_audio_track_id', 'audio_video_anchors', ['audio_track_id'])
    op.create_index('ix_audio_video_anchors_video_clip_id', 'audio_video_anchors', ['video_clip_id'])

    # TimelineEntry Foreign Keys
    op.create_index('ix_timeline_entries_project_id', 'timeline_entries', ['project_id'])
    op.create_index('ix_timeline_entries_audio_track_id', 'timeline_entries', ['audio_track_id'])
    op.create_index('ix_timeline_entries_video_clip_id', 'timeline_entries', ['video_clip_id'])

    # StructureSegment Foreign Keys
    op.create_index('ix_structure_segments_audio_track_id', 'structure_segments', ['audio_track_id'])

    # HotCue Foreign Keys
    op.create_index('ix_hot_cues_audio_track_id', 'hot_cues', ['audio_track_id'])

    # ClipAnchor Foreign Keys
    op.create_index('ix_clip_anchors_timeline_entry_id', 'clip_anchors', ['timeline_entry_id'])


def downgrade():
    """Entfernt die Indizes."""
    op.drop_index('ix_audio_tracks_project_id', table_name='audio_tracks')
    op.drop_index('ix_video_clips_project_id', table_name='video_clips')
    op.drop_index('ix_scenes_video_clip_id', table_name='scenes')
    op.drop_index('ix_beatgrids_audio_track_id', table_name='beatgrids')
    op.drop_index('ix_waveform_data_audio_track_id', table_name='waveform_data')
    op.drop_index('ix_pacing_blueprints_project_id', table_name='pacing_blueprints')
    op.drop_index('ix_audio_video_anchors_audio_track_id', table_name='audio_video_anchors')
    op.drop_index('ix_audio_video_anchors_video_clip_id', table_name='audio_video_anchors')
    op.drop_index('ix_timeline_entries_project_id', table_name='timeline_entries')
    op.drop_index('ix_timeline_entries_audio_track_id', table_name='timeline_entries')
    op.drop_index('ix_timeline_entries_video_clip_id', table_name='timeline_entries')
    op.drop_index('ix_structure_segments_audio_track_id', table_name='structure_segments')
    op.drop_index('ix_hot_cues_audio_track_id', table_name='hot_cues')
    op.drop_index('ix_clip_anchors_timeline_entry_id', table_name='clip_anchors')
