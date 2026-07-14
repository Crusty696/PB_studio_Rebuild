"""add_beatgrids_rhythm_analysis_fields

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-14

B-235: Die drei RhythmAnalysis-Felder ``swing_ratio``, ``groove_confidence``
und ``onset_strength_curve`` (``services/onset_rhythm_service.py`` Dataclass
``RhythmAnalysis``) wurden bislang NICHT in der ``beatgrids``-Tabelle
persistiert. ``OnsetRhythmService.load_from_db()`` konnte sie nach einem
DB-Reload nicht restaurieren -> Rueckfall auf die Dataclass-Defaults
(swing_ratio=0.5, groove_confidence=0.0, onset_strength_curve=[]).

Diese Revision ruestet die drei Spalten nach:
- ``swing_ratio``          Float, server_default "0.5"  (Backfill Bestands-Rows)
- ``groove_confidence``    Float, server_default "0.0"  (Backfill Bestands-Rows)
- ``onset_strength_curve`` JSON  (analog onset_kick_data/onset_snare_data/...)

Fuer SQLite via ``op.batch_alter_table`` (ADD COLUMN im Copy-and-Move-Batch).
Idempotent per PRAGMA-Check — konsistent mit der Vorgaenger-Revision
``a7b8c9d0e1f2`` (add_beatgrids_stem_weighted_energy).
"""
from __future__ import annotations

import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

logger = logging.getLogger("alembic.migrate.add_beatgrids_rhythm_analysis_fields")

# revision identifiers, used by Alembic.
revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, table_name: str) -> bool:
    return table_name in set(inspect(bind).get_table_names())


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    rows = bind.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return any(row[1] == column_name for row in rows)


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "beatgrids"):
        logger.info("beatgrids table missing — skipping (fresh DB creates it via baseline)")
        return

    with op.batch_alter_table("beatgrids") as batch_op:
        if not _column_exists(bind, "beatgrids", "swing_ratio"):
            batch_op.add_column(
                sa.Column("swing_ratio", sa.Float(), nullable=True, server_default="0.5")
            )
            logger.info("Added beatgrids.swing_ratio")
        else:
            logger.info("beatgrids.swing_ratio already exists — skipping")

        if not _column_exists(bind, "beatgrids", "groove_confidence"):
            batch_op.add_column(
                sa.Column("groove_confidence", sa.Float(), nullable=True, server_default="0.0")
            )
            logger.info("Added beatgrids.groove_confidence")
        else:
            logger.info("beatgrids.groove_confidence already exists — skipping")

        if not _column_exists(bind, "beatgrids", "onset_strength_curve"):
            batch_op.add_column(
                sa.Column("onset_strength_curve", sa.JSON(), nullable=True)
            )
            logger.info("Added beatgrids.onset_strength_curve")
        else:
            logger.info("beatgrids.onset_strength_curve already exists — skipping")


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "beatgrids"):
        return
    try:
        with op.batch_alter_table("beatgrids") as batch_op:
            if _column_exists(bind, "beatgrids", "onset_strength_curve"):
                batch_op.drop_column("onset_strength_curve")
            if _column_exists(bind, "beatgrids", "groove_confidence"):
                batch_op.drop_column("groove_confidence")
            if _column_exists(bind, "beatgrids", "swing_ratio"):
                batch_op.drop_column("swing_ratio")
    except Exception as e:  # broad: SQLite < 3.35 kann DROP COLUMN nicht
        logger.warning(
            "drop_column beatgrids rhythm-analysis-fields fehlgeschlagen "
            "(SQLite < 3.35?): %s",
            e,
        )
