"""add_av_pacing_data_table

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-07-15

AVPacingService (``services/av_pacing_service.py``) rechnet pro Audio-Track vier
Zeitreihen im 0.1s-Raster (``spectral_centroid``, ``spectral_flux``,
``stereo_width``, ``percussive_ratio`` — letzteres via HPSS). Die AVPacingStage
(``services/audio_pipeline/stages.py``) lief zwar in DEFAULT_STAGE_ORDER, warf
das Ergebnis aber weg: nur ``len(times_sec)`` landete im Pipeline-Result. Kein
_persist_to_track, keine Spalte, kein Consumer.

Diese Revision legt die Zieltabelle an. Bewusst eine EIGENE 1:1-Tabelle statt
JSON-Spalten auf ``audio_tracks``:
- Ein 60-min-Track ergibt bei 0.1s-Raster ~36.000 Werte je Kurve. Persistiert
  wird downgesampelt (jeder 4. Frame, Vorbild ``services/onset_rhythm_service``
  ``.py:213``) -> 0.4s-Raster, ~9.000 Werte je Kurve.
- ``audio_tracks.energy_curve`` ist mit ~3.600 Werten bereits als Freeze-Ursache
  dokumentiert (``services/ingest_service.py:575``, P8-FREEZE-FIX). Eine weitere
  Blob-Spalte auf derselben Tabelle wuerde diese Klasse (B-090) neu einbauen.
- Vorbild fuer die Auslagerung: ``waveform_data`` (eigene 1:1-Tabelle).

Zusaetzlich ``rms_curve`` + ``rms_hop_sec``: die RMS-Energie faellt im selben
librosa-Stream ab (kein zusaetzliches Audio-Laden) und wird bewusst in VOLLER
0.1s-Aufloesung gespeichert — Konsument ist ``services/pacing/audio_video_curves``
(``DEFAULT_BIN_MS = 100``) fuer den kurvenbasierten Energy-Match gegen die
Clip-Motion-Kurve, der auf einem 0.4s-Raster nicht funktionieren wuerde. Daher
zwei Raster in einer Tabelle: ``hop_sec`` fuer die vier Kurven, ``rms_hop_sec``
fuer ``rms_curve``. Beide nullable — Zeilen ohne RMS bleiben gueltig.

Die Relationship nutzt ``lazy='select'`` (nicht ``'joined'`` wie die Nachbarn) —
die Kurven werden nur geladen, wenn ein Consumer sie anfasst.

Idempotent per Inspector-Check — konsistent mit der Vorgaenger-Revision
``c9d0e1f2a3b4``.
"""
from __future__ import annotations

import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

logger = logging.getLogger("alembic.migrate.add_av_pacing_data_table")

# revision identifiers, used by Alembic.
revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, table_name: str) -> bool:
    return table_name in set(inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "audio_tracks"):
        logger.info(
            "audio_tracks table missing — skipping (fresh DB creates it via baseline)"
        )
        return
    if _table_exists(bind, "av_pacing_data"):
        logger.info("av_pacing_data already exists — skipping")
        return

    op.create_table(
        "av_pacing_data",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("audio_track_id", sa.Integer(), nullable=False),
        sa.Column("hop_sec", sa.Float(), nullable=False, server_default="0.4"),
        sa.Column("num_samples", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("times_sec", sa.JSON(), nullable=False),
        sa.Column("spectral_centroid", sa.JSON(), nullable=False),
        sa.Column("spectral_flux", sa.JSON(), nullable=False),
        sa.Column("stereo_width", sa.JSON(), nullable=False),
        sa.Column("percussive_ratio", sa.JSON(), nullable=False),
        # RMS in voller 0.1s-Aufloesung (eigenes Raster -> eigenes Hop-Feld).
        # Konsument: services/pacing/audio_video_curves (DEFAULT_BIN_MS = 100)
        # fuer den kurvenbasierten Energy-Match gegen die Clip-Motion-Kurve.
        sa.Column("rms_hop_sec", sa.Float(), nullable=True),
        sa.Column("rms_curve", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["audio_track_id"], ["audio_tracks.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("audio_track_id"),
    )
    op.create_index("idx_av_pacing_audio", "av_pacing_data", ["audio_track_id"])
    logger.info("Created table av_pacing_data")


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "av_pacing_data"):
        return
    try:
        op.drop_index("idx_av_pacing_audio", table_name="av_pacing_data")
    except Exception as e:  # broad: Index kann bereits fehlen
        logger.warning("drop_index idx_av_pacing_audio fehlgeschlagen: %s", e)
    op.drop_table("av_pacing_data")
