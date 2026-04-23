"""extend_analysis_status_and_pacing_memory

Revision ID: e670c6bc097c
Revises: 15b79edf1d76
Create Date: 2026-04-23 13:07:19.037562

Data migration that:
1. Adds 'structure_enrichment' rows to analysis_status for every existing video.
2. Best-effort imports AIPacingMemory rows → mem_learned_pattern (idempotent).
3. Records a system marker row so a second upgrade head is a no-op.

downgrade() removes the marker and the structure_enrichment rows added above.
It does NOT delete AIPacingMemory rows or mem_learned_pattern rows — data
consumed is considered consumed (safe to leave; avoids losing imported
knowledge on accidental downgrade).
"""
from __future__ import annotations

import logging
import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

logger = logging.getLogger("alembic.migrate.extend_analysis_status_and_pacing_memory")

# revision identifiers, used by Alembic.
revision: str = 'e670c6bc097c'
down_revision: Union[str, None] = '15b79edf1d76'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Sentinel that marks "this migration has already run its data work".
_SYSTEM_MEDIA_TYPE = "__system__"
_SYSTEM_MEDIA_ID = 0
_MARKER_STEP = "aipacingmemory_import_v1"
_STRUCT_STEP = "structure_enrichment"


def _now() -> str:
    """Return ISO-8601 timestamp for SQLite text datetime columns."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def upgrade() -> None:
    """
    1. Idempotency guard — skip if marker already present.
    2. Add structure_enrichment rows for every existing video in analysis_status.
    3. Best-effort import AIPacingMemory → mem_learned_pattern (confidence=0.3).
    4. Insert marker row.
    """
    bind = op.get_bind()

    # ── 1. Idempotency guard ─────────────────────────────────────────────────
    marker_exists = bind.execute(
        text(
            "SELECT COUNT(*) FROM analysis_status "
            "WHERE media_type = :mt AND media_id = :mid AND step_key = :step AND status = 'done'"
        ),
        {"mt": _SYSTEM_MEDIA_TYPE, "mid": _SYSTEM_MEDIA_ID, "step": _MARKER_STEP},
    ).scalar()

    if marker_exists:
        logger.info(
            "Migration e670c6bc097c: idempotency marker found — skipping data work."
        )
        return

    # ── 2. Add structure_enrichment rows for every existing video ────────────
    # Collect all distinct media_ids for media_type='video' in analysis_status.
    video_ids_rows = bind.execute(
        text(
            "SELECT DISTINCT media_id FROM analysis_status WHERE media_type = 'video'"
        )
    ).fetchall()

    now_str = _now()
    inserted_count = 0
    for row in video_ids_rows:
        media_id = row[0]
        # Skip if this (video, media_id, structure_enrichment) row already exists.
        existing = bind.execute(
            text(
                "SELECT COUNT(*) FROM analysis_status "
                "WHERE media_type = 'video' AND media_id = :mid AND step_key = :step"
            ),
            {"mid": media_id, "step": _STRUCT_STEP},
        ).scalar()
        if not existing:
            bind.execute(
                text(
                    "INSERT INTO analysis_status "
                    "(media_type, media_id, step_key, status, started_at) "
                    "VALUES ('video', :mid, :step, 'pending', :now)"
                ),
                {"mid": media_id, "step": _STRUCT_STEP, "now": now_str},
            )
            inserted_count += 1

    logger.info(
        "Migration e670c6bc097c: inserted %d structure_enrichment rows.", inserted_count
    )

    # ── 3. Best-effort AIPacingMemory → mem_learned_pattern import ───────────
    # AIPacingMemory columns: id, created_at, bpm, bass_energy, drum_energy,
    # overall_energy, mood, audio_time, raft_motion, siglip_tags, cut_type,
    # crossfade_duration, section_type, scene_id, audio_track_id, label.
    # We map each row to a context_preference pattern in mem_learned_pattern.
    # confidence=0.3 (conservative; imported from a different schema).
    try:
        apm_rows = bind.execute(
            text(
                "SELECT id, bpm, bass_energy, drum_energy, overall_energy, "
                "mood, section_type, raft_motion, siglip_tags, scene_id "
                "FROM ai_pacing_memory"
            )
        ).fetchall()

        imported = 0
        for apm in apm_rows:
            apm_id, bpm, bass_energy, drum_energy, overall_energy, \
                mood, section_type, raft_motion, siglip_tags, scene_id = apm

            # Build a simple context fingerprint from the legacy columns.
            # Bucket BPM to nearest 5 to avoid float-key fragmentation (Bug-H fix).
            bpm_bucket: int | None = None
            if bpm is not None:
                bpm_bucket = int(round(bpm / 5.0)) * 5

            import json as _json

            context_fp = _json.dumps({
                "source": "aipacingmemory_import_v1",
                "legacy_id": apm_id,
                "bpm_bucket": bpm_bucket,
                "mood": mood,
                "section_type": section_type,
            }, sort_keys=True)

            target_ref = _json.dumps({
                "scene_id": scene_id,
                "raft_motion": raft_motion,
                "siglip_tags": siglip_tags,
            }, sort_keys=True)

            bind.execute(
                text(
                    "INSERT INTO mem_learned_pattern "
                    "(pattern_type, context_fingerprint, target_ref, "
                    " stat_accept_count, stat_reject_count, stat_sample_size, "
                    " confidence, last_updated) "
                    "VALUES ('context_preference', :fp, :tr, 1, 0, 1, 0.3, :now)"
                ),
                {"fp": context_fp, "tr": target_ref, "now": now_str},
            )
            imported += 1

        logger.info(
            "Migration e670c6bc097c: imported %d AIPacingMemory rows → mem_learned_pattern.",
            imported,
        )

    except Exception as exc:  # noqa: BLE001
        # Non-fatal: AIPacingMemory may be empty or table shape unexpected.
        logger.info(
            "Migration e670c6bc097c: AIPacingMemory import skipped (%s). "
            "This is expected when AIPacingMemory is empty or unavailable.",
            exc,
        )

    # ── 4. Marker row ────────────────────────────────────────────────────────
    bind.execute(
        text(
            "INSERT INTO analysis_status "
            "(media_type, media_id, step_key, status, completed_at) "
            "VALUES (:mt, :mid, :step, 'done', :now)"
        ),
        {
            "mt": _SYSTEM_MEDIA_TYPE,
            "mid": _SYSTEM_MEDIA_ID,
            "step": _MARKER_STEP,
            "now": now_str,
        },
    )
    logger.info("Migration e670c6bc097c: marker row inserted — upgrade complete.")


def downgrade() -> None:
    """
    1. Delete the idempotency marker row.
    2. Delete structure_enrichment rows added by upgrade().
    Does NOT delete AIPacingMemory rows or imported mem_learned_pattern rows.
    """
    bind = op.get_bind()

    # Remove marker.
    bind.execute(
        text(
            "DELETE FROM analysis_status "
            "WHERE media_type = :mt AND media_id = :mid AND step_key = :step"
        ),
        {"mt": _SYSTEM_MEDIA_TYPE, "mid": _SYSTEM_MEDIA_ID, "step": _MARKER_STEP},
    )

    # Remove structure_enrichment rows for actual videos (media_type='video').
    # Leave __system__ and other media_types untouched.
    bind.execute(
        text(
            "DELETE FROM analysis_status "
            "WHERE media_type = 'video' AND step_key = :step"
        ),
        {"step": _STRUCT_STEP},
    )

    logger.info("Migration e670c6bc097c: downgrade complete (AIPacingMemory + imported patterns preserved).")
