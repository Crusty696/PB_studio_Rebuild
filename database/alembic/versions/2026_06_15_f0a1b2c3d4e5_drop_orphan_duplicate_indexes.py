"""drop orphan duplicate indexes (ix_timeline_entries_project_id, ix_hotcues_audio_track_id)

These auto-generated ``ix_*`` indexes are legacy leftovers from a former
``index=True`` column definition. The ORM (database/models.py) now declares
only the explicit ``idx_timeline_project`` / ``idx_hotcue_audio`` indexes, so
fresh builds never create the ``ix_*`` duplicates — but long-lived
pb_studio.db files still carry them. This revision removes them idempotently
to bring existing DBs in line with Base.metadata. No-op on fresh DBs.

Revision ID: f0a1b2c3d4e5
Revises: e5f6a7b8c9d0
Create Date: 2026-06-15
"""
from typing import Sequence, Union

from alembic import op

revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# orphan index name -> table
_ORPHANS = {
    "ix_timeline_entries_project_id": "timeline_entries",
    "ix_hotcues_audio_track_id": "hotcues",
}


def _index_exists(index_name: str, table_name: str) -> bool:
    from sqlalchemy import inspect

    inspector = inspect(op.get_bind())
    try:
        names = {idx["name"] for idx in inspector.get_indexes(table_name)}
    except Exception:
        return False
    return index_name in names


def upgrade() -> None:
    for index_name, table_name in _ORPHANS.items():
        if _index_exists(index_name, table_name):
            op.drop_index(index_name, table_name=table_name)


def downgrade() -> None:
    # Re-create the legacy duplicate indexes for a clean rollback.
    if not _index_exists("ix_timeline_entries_project_id", "timeline_entries"):
        op.create_index(
            "ix_timeline_entries_project_id", "timeline_entries", ["project_id"]
        )
    if not _index_exists("ix_hotcues_audio_track_id", "hotcues"):
        op.create_index(
            "ix_hotcues_audio_track_id", "hotcues", ["audio_track_id"]
        )
