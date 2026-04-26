"""Initial schema with soft deletes

Revision ID: beb242bcd1fb
Revises:
Create Date: 2026-04-08 23:57:43.575095

B-181 Fix (Cycle 1): Vorher leere No-Op-Migration. App-Pfad funktionierte
nur weil ``init_db()`` ``Base.metadata.create_all()`` als Safety-Net VOR
Alembic ausführt. Alembic-only-Pfad (CI fresh-DB, frisches Dev-Setup,
``test_full_roundtrip_empty_db``) lief auf ``no such table: audio_tracks``
weil die nachfolgende Migration ``b2c3d4e5f6a7`` ein ALTER TABLE auf eine
nicht-existente Tabelle versuchte.

Lösung: Initial-Migration erstellt das vollständige Baseline-Schema aus
``Base.metadata`` (alle 16 Tabellen die VOR den späteren add_*_table
Migrationen existierten). Folge-Migrationen sind durchgängig idempotent
(``_column_exists``-Checks für ALTER TABLE; create_table nur für neue
Tabellen die hier ausgeklammert sind).

Bestehende, produktiv migrierte Datenbanken sind durch ``stamp`` bereits
auf eine Revision > ``beb242bcd1fb`` gesetzt — diese Migration läuft auf
ihnen NICHT erneut, kein Regressionsrisiko.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'beb242bcd1fb'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tabellen die zur Initial-Zeit (Baseline) existierten. Tabellen die durch
# spätere Migrationen entstanden — ``analysis_status`` (da8d942ad38a),
# ``mem_*`` (15b79edf1d76), ``struct_*`` (b5d5adc80d3a) — werden hier NICHT
# erstellt, sondern bleiben Aufgabe der jeweiligen Folge-Migration.
_INITIAL_TABLES: tuple[str, ...] = (
    "projects",
    "audio_tracks",
    "video_clips",
    "scenes",
    "beatgrids",
    "waveform_data",
    "pacing_blueprints",
    "audio_video_anchors",
    "clip_anchors",
    "ai_pacing_memory",
    "structure_segments",
    "hotcues",
    "model_registry",
    "agent_feedback",
    "style_presets",
    "timeline_entries",
)


def _initial_metadata_subset() -> sa.MetaData:
    """Liefert ein MetaData-Objekt das nur die Initial-Tabellen enthält.

    Wir kopieren die Table-Objekte aus ``database.models.Base.metadata`` in
    eine frische ``MetaData``, damit ``create_all`` / ``drop_all`` exakt die
    Initial-Tabellen-Liste verarbeitet (ohne die später hinzugekommenen).
    """
    from database.models import Base

    subset = sa.MetaData()
    for tname in _INITIAL_TABLES:
        src_table = Base.metadata.tables.get(tname)
        if src_table is None:
            raise RuntimeError(
                f"Initial-Migration: Tabelle '{tname}' fehlt in Base.metadata — "
                f"models.py wurde inkompatibel geändert."
            )
        src_table.to_metadata(subset)
    return subset


def upgrade() -> None:
    """Erzeugt das Baseline-Schema (16 Tabellen) idempotent.

    Idempotenz: Existieren die Tabellen bereits (z. B. weil eine Legacy-DB
    via ``Base.metadata.create_all`` initialisiert und nachträglich gestempelt
    wurde), überspringt SQLAlchemy ihre Erstellung dank ``checkfirst=True``.
    """
    bind = op.get_bind()
    metadata = _initial_metadata_subset()
    metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    """Entfernt das Baseline-Schema in FK-konformer Reihenfolge."""
    bind = op.get_bind()
    metadata = _initial_metadata_subset()
    metadata.drop_all(bind=bind, checkfirst=True)
