"""add_beatgrids_stem_weighted_energy

Revision ID: a7b8c9d0e1f2
Revises: f0a1b2c3d4e5
Create Date: 2026-07-07

AUDIT-FIXPLAN-2026-07-07 / A3 (DB-010): ``beatgrids.stem_weighted_energy``
(P1.7-FIX, ``database/models.py``) wurde nie per Migration nachgeruestet —
weder im Legacy-Block (FROZEN seit B-509) noch in einer Alembic-Revision.
Frische DBs bekommen die Spalte via ``Base.metadata`` in der Baseline;
eine Bestands-DB von vor P1.7 crasht beim Beatgrid-Write mit
``OperationalError: no such column: stem_weighted_energy``.

Scan 2026-07-07 (read-only, 24 lokale Projekt-/Backup-DBs): 0 betroffen —
diese Revision ist PRAEVENTIV fuer alte Backups / von fremden Staenden
wiederhergestellte Projekte. Idempotent per PRAGMA-Check.
"""
from __future__ import annotations

import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

logger = logging.getLogger("alembic.migrate.add_beatgrids_stem_weighted_energy")

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f0a1b2c3d4e5"
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
    if _column_exists(bind, "beatgrids", "stem_weighted_energy"):
        logger.info("beatgrids.stem_weighted_energy already exists — skipping")
        return
    op.add_column(
        "beatgrids", sa.Column("stem_weighted_energy", sa.JSON(), nullable=True)
    )
    logger.info("Added beatgrids.stem_weighted_energy")


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "beatgrids"):
        return
    if not _column_exists(bind, "beatgrids", "stem_weighted_energy"):
        return
    try:
        op.drop_column("beatgrids", "stem_weighted_energy")
    except Exception as e:  # broad: SQLite < 3.35
        logger.warning(
            "drop_column beatgrids.stem_weighted_energy fehlgeschlagen (SQLite < 3.35?): %s",
            e,
        )
