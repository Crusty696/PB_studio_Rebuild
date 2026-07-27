"""add_struct_clip_tags_visual_metrics

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-07-27

Ruestet ``struct_clip_tags`` (PK ``scene_id``, angelegt in Revision
``b5d5adc80d3a``) um zwei Datengruppen nach, fuer die es bisher KEINE
Quelle gab:

1) Bildmetriken pro Szene (Aufgabe 1)
   ``services/brain/bridge_dimensions.py`` bewertet
   ``brightness_match_weight`` und ``color_temp_match_weight`` ueber
   ``ClipCandidate.brightness/.saturation/.color_temp``. Diese Felder wurden
   bis dato konstant mit 0.5 / 0.5 / 0.0 befuellt
   (``brain_v3_service._build_service_candidates``), womit beide Achsen fuer
   alle Kandidaten identisch und wirkungslos waren. Gemessen wird jetzt aus
   den ohnehin vorhandenen Keyframe-JPEGs
   (``services/enrichment/visual_metrics.py``, CPU-only).

   - ``avg_brightness``          REAL  0..1     mittlere Rec.709-Luma
   - ``avg_saturation``          REAL  0..1     mittlere HSV-Saettigung
   - ``color_temp``              REAL  -1..+1   (R-B)/(R+B), warm positiv
   - ``visual_frame_count``      INT            eingeflossene Keyframes
   - ``visual_metrics_version``  TEXT           z.B. "vm1"

   ABGRENZUNG: ``timeline_entries.brightness`` ist ein
   Farbkorrektur-REGLER (User-Eingabe), KEIN Messwert. Er bleibt unberuehrt.

2) Provenienz der Rolle (Aufgabe 2)
   - ``role_source`` TEXT — ``"rule" | "embedding" | "unknown"``.
     Macht sichtbar, ob ``role`` aus ``config/enrichment_rules.yaml``
     (Override-Pfad) oder aus den SigLIP-Prototypen stammt — bzw. warum sie
     ``unknown`` ist. Ohne diese Spalte war der Befund "27/27 Szenen
     ``filler``, weil nie eine Regel traf" aus der DB nicht ablesbar.

Alle Spalten NULLABLE: Bestandszeilen haben keine Werte, bis der
Enrichment-Lauf oder ``scripts/backfill_visual_metrics.py`` sie fuellt.
NULL bedeutet ehrlich "nicht gemessen" — kein stiller 0.5-Default.

SQLite via ``op.batch_alter_table``; idempotent per PRAGMA-Check, gleiches
Muster wie ``c9d0e1f2a3b4`` / ``b8c9d0e1f2a3``.
"""
from __future__ import annotations

import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

logger = logging.getLogger("alembic.migrate.add_struct_clip_tags_visual_metrics")

# revision identifiers, used by Alembic.
revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "struct_clip_tags"

_NEW_COLUMNS: list[tuple[str, sa.types.TypeEngine]] = [
    ("avg_brightness", sa.Float()),
    ("avg_saturation", sa.Float()),
    ("color_temp", sa.Float()),
    ("visual_frame_count", sa.Integer()),
    ("visual_metrics_version", sa.Text()),
    ("role_source", sa.Text()),
]


def _table_exists(bind, table_name: str) -> bool:
    return table_name in set(inspect(bind).get_table_names())


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    rows = bind.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return any(row[1] == column_name for row in rows)


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, _TABLE):
        logger.info(
            "%s fehlt — uebersprungen (frische DB legt sie via b5d5adc80d3a an)",
            _TABLE,
        )
        return

    missing = [
        (name, type_)
        for name, type_ in _NEW_COLUMNS
        if not _column_exists(bind, _TABLE, name)
    ]
    if not missing:
        logger.info("%s: alle Visual-Metrics-Spalten vorhanden — skip", _TABLE)
        return

    with op.batch_alter_table(_TABLE) as batch_op:
        for name, type_ in missing:
            batch_op.add_column(sa.Column(name, type_, nullable=True))
            logger.info("Added %s.%s", _TABLE, name)


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, _TABLE):
        return
    for name, _type in reversed(_NEW_COLUMNS):
        if not _column_exists(bind, _TABLE, name):
            continue
        try:
            with op.batch_alter_table(_TABLE) as batch_op:
                batch_op.drop_column(name)
        except Exception as e:  # broad: SQLite < 3.35 kann DROP COLUMN nicht
            logger.warning(
                "drop_column %s.%s fehlgeschlagen (SQLite < 3.35?): %s",
                _TABLE,
                name,
                e,
            )
