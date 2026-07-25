"""add_soft_delete_timeline_backup

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-07-25

B-706/M1: Restore aus dem Papierkorb stellte die Timeline-Platzierung nicht
wieder her. Der Soft-Delete (``services/ingest_service.py``) loescht
``TimelineEntry`` + ``ClipAnchor`` physisch (damit kein Consumer einen
getrashten Clip referenziert); ``restore_media`` setzte nur ``deleted_at=NULL``
auf den Parent-Rows. Folge: Clip kehrt in die Bibliothek zurueck, ist aber von
der Timeline verschwunden (stiller Verlust).

Diese Revision legt die Backup-Tabelle an, in die der Soft-Delete einen
JSON-Snapshot der geloeschten Platzierung schreibt und aus der restore_media sie
neu anlegt. Bewusst eine EIGENE Tabelle statt Blob-Spalten auf den Hot-Media-
Tabellen (Konvention, vgl. ``av_pacing_data`` / Vorgaenger-Revision).

Idempotent per Inspector-Check — konsistent mit ``d0e1f2a3b4c5``.
"""
from __future__ import annotations

import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

logger = logging.getLogger("alembic.migrate.add_soft_delete_timeline_backup")

# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, table_name: str) -> bool:
    return table_name in set(inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "projects"):
        logger.info(
            "projects table missing — skipping (fresh DB creates all via baseline)"
        )
        return
    if _table_exists(bind, "soft_delete_timeline_backup"):
        logger.info("soft_delete_timeline_backup already exists — skipping")
        return

    op.create_table(
        "soft_delete_timeline_backup",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.String(), nullable=False),
        sa.Column("media_id", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_sd_timeline_backup_media",
        "soft_delete_timeline_backup",
        ["media_type", "media_id"],
    )
    logger.info("Created table soft_delete_timeline_backup")


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "soft_delete_timeline_backup"):
        return
    try:
        op.drop_index(
            "idx_sd_timeline_backup_media",
            table_name="soft_delete_timeline_backup",
        )
    except Exception as e:  # broad: Index kann bereits fehlen
        logger.warning("drop_index idx_sd_timeline_backup_media fehlgeschlagen: %s", e)
    op.drop_table("soft_delete_timeline_backup")
