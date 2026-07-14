"""add_audio_tracks_acoustic_metadata

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-15

B-494: Die Stem-SNR-Qualitaetsmetrik (``services/pacing_beat_grid.py``
``compute_stem_snr`` -> ``StemSNR`` mit ``drums/bass/vocals/other``) wurde
bislang nur fluechtig in ``pacing_service.py`` verwendet, aber NIE persistiert.
Die Stems-UI (``ui/workspaces/stems_workspace.py`` ``_extract_snr``) las
``acoustic_metadata`` -> es gab jedoch keine DB-Spalte -> Subtab zeigte immer
"nicht verfuegbar".

Diese Revision ruestet die Spalte nach:
- ``acoustic_metadata`` JSON, nullable — winziges Dict
  ``{"stem_snr": {"drums": <float>, "bass": <float>, "vocals": <float>,
  "other": <float>}}`` (kein Blob). Wird nach erfolgreichem Demucs-StemGen in
  ``services/ai_audio_service.py`` ``separate_and_store`` geschrieben.

Fuer SQLite via ``op.batch_alter_table`` (ADD COLUMN im Copy-and-Move-Batch).
Idempotent per PRAGMA-Check — konsistent mit der Vorgaenger-Revision
``b8c9d0e1f2a3`` (add_beatgrids_rhythm_analysis_fields).
"""
from __future__ import annotations

import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

logger = logging.getLogger("alembic.migrate.add_audio_tracks_acoustic_metadata")

# revision identifiers, used by Alembic.
revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, table_name: str) -> bool:
    return table_name in set(inspect(bind).get_table_names())


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    rows = bind.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return any(row[1] == column_name for row in rows)


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "audio_tracks"):
        logger.info("audio_tracks table missing — skipping (fresh DB creates it via baseline)")
        return

    with op.batch_alter_table("audio_tracks") as batch_op:
        if not _column_exists(bind, "audio_tracks", "acoustic_metadata"):
            batch_op.add_column(
                sa.Column("acoustic_metadata", sa.JSON(), nullable=True)
            )
            logger.info("Added audio_tracks.acoustic_metadata")
        else:
            logger.info("audio_tracks.acoustic_metadata already exists — skipping")


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "audio_tracks"):
        return
    try:
        with op.batch_alter_table("audio_tracks") as batch_op:
            if _column_exists(bind, "audio_tracks", "acoustic_metadata"):
                batch_op.drop_column("acoustic_metadata")
    except Exception as e:  # broad: SQLite < 3.35 kann DROP COLUMN nicht
        logger.warning(
            "drop_column audio_tracks.acoustic_metadata fehlgeschlagen "
            "(SQLite < 3.35?): %s",
            e,
        )
