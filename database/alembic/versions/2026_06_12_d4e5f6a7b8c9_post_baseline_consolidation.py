"""post_baseline_consolidation

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-12

B-509 (CRF-011): Alembic-Drift-Konsolidierung. Seit Revision c3d4e5f6a7b8
(2026-04-30) lebten alle neueren Schema-Aenderungen NUR als Hand-ALTERs in
``database/migrations.py::_run_legacy_migrations`` (Z.415-453, 607-638):

- ``timeline_entries.locked`` (SCHNITT-Redesign 2026-05-09)
- Tabelle ``timeline_snapshots`` + Index ``idx_snapshot_project_version``
- Tabelle ``project_notes``
- video_pipeline-Spalten auf ``video_clips`` (video_pipeline_status,
  video_pipeline_checkpoint_path, stream_sha256, embeddings_path,
  motion_path, proxy_status) + Indizes ``ix_video_clips_stream_sha256``,
  ``ix_video_clips_pipeline_status``
- Pipeline-Spalten auf ``scenes`` (scene_index, keyframe_paths,
  embedding_indices) + Index ``ix_scenes_scene_index``

Diese Revision macht die Alembic-Kette wieder zur vollstaendigen
Schema-Wahrheit. ALLE Schritte sind idempotent (Inspector-/PRAGMA-Checks):

- Bestands-DBs haben alle Teile bereits durch die Hand-ALTERs -> skip.
- Frische Alembic-only-DBs haben die SPALTEN bereits, weil die Baseline
  ``beb242bcd1fb`` ihre 16 Initial-Tabellen dynamisch aus dem aktuellen
  ``Base.metadata`` erzeugt — es fehlen dort nur ``timeline_snapshots``
  und ``project_notes`` (per Inventar 2026-06-12 verifiziert).

Die Legacy-Fixups in migrations.py bleiben fuer alte Bestands-DBs erhalten,
sind aber ab jetzt FROZEN (B-509) — neue Schemaaenderungen nur noch via
Alembic.
"""
from __future__ import annotations

import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

logger = logging.getLogger("alembic.migrate.post_baseline_consolidation")

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Idempotenz-Helfer
# ---------------------------------------------------------------------------

def _table_exists(bind, table_name: str) -> bool:
    return table_name in set(inspect(bind).get_table_names())


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    rows = bind.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return any(row[1] == column_name for row in rows)


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    rows = bind.execute(text(f"PRAGMA index_list({table_name})")).fetchall()
    return any(row[1] == index_name for row in rows)


# Spalten, die bisher nur via migrations.py-Hand-ALTERs existierten.
_VIDEO_CLIPS_COLUMNS = (
    ("video_pipeline_status", sa.String()),
    ("video_pipeline_checkpoint_path", sa.String()),
    ("stream_sha256", sa.String()),
    ("embeddings_path", sa.String()),
    ("motion_path", sa.String()),
    ("proxy_status", sa.String()),
)

_SCENES_COLUMNS = (
    ("scene_index", sa.Integer()),
    ("keyframe_paths", sa.JSON()),
    ("embedding_indices", sa.JSON()),
)


def upgrade() -> None:
    bind = op.get_bind()

    # ── 1. timeline_snapshots (SCHNITT-Redesign 2026-05-09) ────────────────
    if not _table_exists(bind, "timeline_snapshots"):
        op.create_table(
            "timeline_snapshots",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("label", sa.String(), nullable=True),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["project_id"], ["projects.id"], ondelete="CASCADE"
            ),
        )
        logger.info("Created table timeline_snapshots")
    else:
        logger.info("timeline_snapshots already exists — skipping")

    if not _index_exists(bind, "timeline_snapshots", "idx_snapshot_project_version"):
        op.create_index(
            "idx_snapshot_project_version",
            "timeline_snapshots",
            ["project_id", "version"],
        )
        logger.info("Created index idx_snapshot_project_version")

    # ── 2. project_notes (SCHNITT-Redesign 2026-05-09 Task 1.3) ────────────
    if not _table_exists(bind, "project_notes"):
        op.create_table(
            "project_notes",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("content_md", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("project_id", name="uq_project_notes_project_id"),
            sa.ForeignKeyConstraint(
                ["project_id"], ["projects.id"], ondelete="CASCADE"
            ),
        )
        logger.info("Created table project_notes")
    else:
        logger.info("project_notes already exists — skipping")

    # ── 3. timeline_entries.locked (SCHNITT-Redesign 2026-05-09) ───────────
    if _table_exists(bind, "timeline_entries"):
        if not _column_exists(bind, "timeline_entries", "locked"):
            op.add_column(
                "timeline_entries",
                sa.Column(
                    "locked", sa.Boolean(), nullable=False,
                    server_default=sa.text("0"),
                ),
            )
            logger.info("Added timeline_entries.locked")
        else:
            logger.info("timeline_entries.locked already exists — skipping")

    # ── 4. video_clips Pipeline-Spalten (VIDEO-PIPELINE-ENGINE Phase 01) ───
    if _table_exists(bind, "video_clips"):
        for col_name, col_type in _VIDEO_CLIPS_COLUMNS:
            if _column_exists(bind, "video_clips", col_name):
                logger.info("video_clips.%s already exists — skipping", col_name)
                continue
            op.add_column(
                "video_clips", sa.Column(col_name, col_type, nullable=True)
            )
            logger.info("Added video_clips.%s", col_name)

        if not _index_exists(bind, "video_clips", "ix_video_clips_stream_sha256"):
            op.create_index(
                "ix_video_clips_stream_sha256", "video_clips", ["stream_sha256"]
            )
        if not _index_exists(bind, "video_clips", "ix_video_clips_pipeline_status"):
            op.create_index(
                "ix_video_clips_pipeline_status",
                "video_clips",
                ["video_pipeline_status"],
            )

    # ── 5. scenes Pipeline-Spalten (VIDEO-PIPELINE-ENGINE Phase 01) ────────
    if _table_exists(bind, "scenes"):
        for col_name, col_type in _SCENES_COLUMNS:
            if _column_exists(bind, "scenes", col_name):
                logger.info("scenes.%s already exists — skipping", col_name)
                continue
            op.add_column("scenes", sa.Column(col_name, col_type, nullable=True))
            logger.info("Added scenes.%s", col_name)

        if not _index_exists(bind, "scenes", "ix_scenes_scene_index"):
            op.create_index(
                "ix_scenes_scene_index", "scenes", ["video_clip_id", "scene_index"]
            )


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "scenes"):
        if _index_exists(bind, "scenes", "ix_scenes_scene_index"):
            op.drop_index("ix_scenes_scene_index", table_name="scenes")
        for col_name, _col_type in reversed(_SCENES_COLUMNS):
            if not _column_exists(bind, "scenes", col_name):
                continue
            try:
                op.drop_column("scenes", col_name)
            except Exception as e:  # broad: SQLite < 3.35
                logger.warning(
                    "drop_column scenes.%s fehlgeschlagen (SQLite < 3.35?): %s",
                    col_name, e,
                )

    if _table_exists(bind, "video_clips"):
        if _index_exists(bind, "video_clips", "ix_video_clips_pipeline_status"):
            op.drop_index("ix_video_clips_pipeline_status", table_name="video_clips")
        if _index_exists(bind, "video_clips", "ix_video_clips_stream_sha256"):
            op.drop_index("ix_video_clips_stream_sha256", table_name="video_clips")
        for col_name, _col_type in reversed(_VIDEO_CLIPS_COLUMNS):
            if not _column_exists(bind, "video_clips", col_name):
                continue
            try:
                op.drop_column("video_clips", col_name)
            except Exception as e:  # broad: SQLite < 3.35
                logger.warning(
                    "drop_column video_clips.%s fehlgeschlagen (SQLite < 3.35?): %s",
                    col_name, e,
                )

    if _table_exists(bind, "timeline_entries") and _column_exists(
        bind, "timeline_entries", "locked"
    ):
        try:
            op.drop_column("timeline_entries", "locked")
        except Exception as e:  # broad: SQLite < 3.35
            logger.warning(
                "drop_column timeline_entries.locked fehlgeschlagen: %s", e
            )

    if _table_exists(bind, "project_notes"):
        op.drop_table("project_notes")

    if _table_exists(bind, "timeline_snapshots"):
        if _index_exists(bind, "timeline_snapshots", "idx_snapshot_project_version"):
            op.drop_index(
                "idx_snapshot_project_version", table_name="timeline_snapshots"
            )
        op.drop_table("timeline_snapshots")
