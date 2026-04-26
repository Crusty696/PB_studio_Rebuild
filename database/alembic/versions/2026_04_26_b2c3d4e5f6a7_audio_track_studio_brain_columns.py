"""audio_track_studio_brain_columns

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-26

Cycle 14 / Option A: Studio-Brain Bridge.
Erweitert audio_tracks um drei Skalar-Spalten die der AudioContext-Builder
braucht — vorher als Felder im build_audio_context() abgefragt aber nicht
im Schema (Bug-Hunter BUG-2).

- sub_genre (TEXT, nullable): Sub-Genre-Tag (z.B. "progressive_psy")
- spectral_hash (TEXT, nullable): 8-Band-Signatur-Hash für Context-Fingerprint
- harmonic_tension (REAL, nullable): Skalar = mean(harmonic_tension_curve)

Idempotent über PRAGMA-table_info-Check.
"""
from __future__ import annotations

import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

logger = logging.getLogger("alembic.migrate.audio_track_studio_brain_columns")

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NEW_COLUMNS = (
    ("sub_genre", sa.String()),
    ("spectral_hash", sa.String()),
    ("harmonic_tension", sa.Float()),
)


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    rows = bind.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return any(row[1] == column_name for row in rows)


def upgrade() -> None:
    bind = op.get_bind()
    for col_name, col_type in _NEW_COLUMNS:
        if _column_exists(bind, "audio_tracks", col_name):
            logger.info("audio_tracks.%s already exists — skipping", col_name)
            continue
        op.add_column(
            "audio_tracks",
            sa.Column(col_name, col_type, nullable=True),
        )
        logger.info("Added audio_tracks.%s", col_name)


def downgrade() -> None:
    bind = op.get_bind()
    for col_name, _col_type in reversed(_NEW_COLUMNS):
        if not _column_exists(bind, "audio_tracks", col_name):
            continue
        try:
            op.drop_column("audio_tracks", col_name)
        except Exception as e:  # broad: SQLite < 3.35
            logger.warning(
                "drop_column %s fehlgeschlagen (SQLite < 3.35?): %s. "
                "Spalte bleibt — funktional unkritisch.", col_name, e,
            )
