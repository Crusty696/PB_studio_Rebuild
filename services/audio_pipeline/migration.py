"""Plan: AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17.

T8.1 + T8.2: Backwards-Compat Migration alter Projekte.

- DB-Spalte ``stem_pipeline_status`` (R-09 neuer Name) auf ``audio_tracks``.
- Lazy-Trigger: alte Projekte ohne stem_pipeline_status='done' bekommen beim
  ersten Analyze-Call StemGen-Trigger.
- Backlog-Threshold (R-16): bei >10 Tracks ohne 'done' UND >1h Audio total
  Confirm-Dialog-Signal an UI.
"""
from __future__ import annotations

from typing import Iterable

# Backlog-Confirm-Threshold
BACKLOG_TRACK_THRESHOLD = 10
BACKLOG_DURATION_SEC_THRESHOLD = 3600  # 1h


def column_exists(connection, table: str, column: str) -> bool:
    """Pragma-Check fuer SQLite-Spalten-Existenz."""
    cursor = connection.execute(f"PRAGMA table_info({table})")
    cols = [row[1] for row in cursor.fetchall()]
    return column in cols


def add_stem_pipeline_status_column(connection) -> bool:
    """T8.1: ALTER TABLE audio_tracks ADD COLUMN stem_pipeline_status TEXT DEFAULT NULL.

    Idempotent: wenn Spalte schon existiert, no-op.
    Returns True wenn Spalte hinzugefuegt wurde.
    """
    if column_exists(connection, "audio_tracks", "stem_pipeline_status"):
        return False
    connection.execute(
        "ALTER TABLE audio_tracks ADD COLUMN stem_pipeline_status TEXT DEFAULT NULL"
    )
    connection.commit()
    return True


def needs_lazy_stemgen(track) -> bool:
    """T8.2: alte Tracks ohne stem_pipeline_status='done' triggern StemGen lazy."""
    status = getattr(track, "stem_pipeline_status", None)
    return status != "done"


def compute_backlog(tracks: Iterable) -> tuple[int, int]:
    """R-16: Backlog (Anzahl Tracks ohne 'done', Summe Duration in Sekunden).

    Returns: (track_count, total_duration_sec)
    """
    count = 0
    total_sec = 0
    for t in tracks:
        if needs_lazy_stemgen(t):
            count += 1
            total_sec += int(getattr(t, "duration_seconds", 0) or 0)
    return count, total_sec


def backlog_requires_confirm(track_count: int, duration_sec: int) -> bool:
    """R-16: User-Confirm wenn Backlog Threshold ueberschreitet."""
    return (track_count > BACKLOG_TRACK_THRESHOLD
            or duration_sec > BACKLOG_DURATION_SEC_THRESHOLD)
