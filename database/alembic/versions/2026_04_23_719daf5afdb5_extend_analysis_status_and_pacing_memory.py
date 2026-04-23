"""extend_analysis_status_and_pacing_memory

Revision ID: 719daf5afdb5
Revises: 7b8a0dfc29a0
Create Date: 2026-04-23 09:24:21.490446
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '719daf5afdb5'
down_revision: Union[str, None] = '7b8a0dfc29a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if target tables exist (important for tests on empty DB)
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    # 1. Extension of AnalysisStatus: Add structure_enrichment for all existing VideoClips
    if "video_clips" in tables and "analysis_status" in tables:
        op.execute(
            "INSERT INTO analysis_status (media_type, media_id, step_key, status) "
            "SELECT 'video', id, 'structure_enrichment', 'pending' "
            "FROM video_clips "
            "WHERE id NOT IN ("
            "    SELECT media_id FROM analysis_status "
            "    WHERE media_type='video' AND step_key='structure_enrichment'"
            ")"
        )

    # 2. Data Migration from AIPacingMemory to mem_learned_pattern
    if "analysis_status" in tables and "ai_pacing_memory" in tables and "mem_learned_pattern" in tables:
        # Check for migration marker to ensure idempotency
        marker_exists = connection.execute(
            sa.text("SELECT 1 FROM analysis_status WHERE media_type='__system__' AND step_key='legacy_pacing_migration_done'")
        ).scalar()

        if not marker_exists:
            # Perform best-effort data migration
            op.execute(
                """
                INSERT INTO mem_learned_pattern (
                    pattern_type,
                    context_fingerprint,
                    target_ref,
                    stat_accept_count,
                    stat_reject_count,
                    stat_sample_size,
                    confidence,
                    last_updated
                )
                SELECT
                    'legacy_ai_memory',
                    json_object(
                        'bpm', bpm,
                        'bass_energy', bass_energy,
                        'drum_energy', drum_energy,
                        'overall_energy', overall_energy,
                        'mood', mood,
                        'audio_time', audio_time,
                        'section_type', section_type
                    ),
                    json_object(
                        'scene_id', scene_id,
                        'cut_type', cut_type,
                        'crossfade_duration', crossfade_duration,
                        'siglip_tags', json(COALESCE(siglip_tags, '[]'))
                    ),
                    1,
                    0,
                    1,
                    0.5,
                    COALESCE(created_at, CURRENT_TIMESTAMP)
                FROM ai_pacing_memory;
                """
            )
            
            # Set migration marker
            op.execute(
                "INSERT INTO analysis_status (media_type, media_id, step_key, status, completed_at) "
                "VALUES ('__system__', 0, 'legacy_pacing_migration_done', 'done', CURRENT_TIMESTAMP)"
            )


def downgrade() -> None:
    # 1. Remove the migration marker
    op.execute("DELETE FROM analysis_status WHERE media_type='__system__' AND step_key='legacy_pacing_migration_done'")
    
    # 2. Remove the added AnalysisStatus rows for structure_enrichment
    op.execute("DELETE FROM analysis_status WHERE media_type='video' AND step_key='structure_enrichment'")
    
    # Note: We do NOT delete the AIPacingMemory table as per requirements.
    # We also don't automatically delete the migrated rows in mem_learned_pattern 
    # to avoid accidental data loss if the migration is rolled back and re-applied,
    # unless specifically asked. The task says "downgrade() reverses the changes 
    # (removes the added AnalysisStatus rows and marker, but does NOT delete the AIPacingMemory table)".
