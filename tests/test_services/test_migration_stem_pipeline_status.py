"""Plan: AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17

T8.1 + T8.2: Migration audio_tracks.stem_pipeline_status + Lazy-Trigger + Backlog.
"""
from __future__ import annotations

import sqlite3
from types import SimpleNamespace
import pytest


def _make_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE audio_tracks (
            id INTEGER PRIMARY KEY,
            file_path TEXT,
            duration_seconds INTEGER
        )
    """)
    conn.execute("INSERT INTO audio_tracks (id, file_path, duration_seconds) VALUES (1, '/a.wav', 300)")
    conn.commit()
    return conn


def test_column_exists_pragma():
    from services.audio_pipeline.migration import column_exists
    conn = _make_conn()
    assert column_exists(conn, "audio_tracks", "file_path") is True
    assert column_exists(conn, "audio_tracks", "stem_pipeline_status") is False


def test_add_stem_pipeline_status_column_adds_with_default():
    from services.audio_pipeline.migration import add_stem_pipeline_status_column, column_exists
    conn = _make_conn()
    added = add_stem_pipeline_status_column(conn)
    assert added is True
    assert column_exists(conn, "audio_tracks", "stem_pipeline_status") is True
    # Default ist NULL
    cur = conn.execute("SELECT stem_pipeline_status FROM audio_tracks WHERE id=1")
    assert cur.fetchone()[0] is None


def test_add_stem_pipeline_status_column_idempotent():
    from services.audio_pipeline.migration import add_stem_pipeline_status_column
    conn = _make_conn()
    add_stem_pipeline_status_column(conn)
    # zweiter Aufruf no-op
    added2 = add_stem_pipeline_status_column(conn)
    assert added2 is False


def test_needs_lazy_stemgen_true_when_status_none():
    from services.audio_pipeline.migration import needs_lazy_stemgen
    t = SimpleNamespace(stem_pipeline_status=None)
    assert needs_lazy_stemgen(t) is True


def test_needs_lazy_stemgen_false_when_done():
    from services.audio_pipeline.migration import needs_lazy_stemgen
    t = SimpleNamespace(stem_pipeline_status="done")
    assert needs_lazy_stemgen(t) is False


def test_compute_backlog_counts_and_sums_duration():
    from services.audio_pipeline.migration import compute_backlog
    tracks = [
        SimpleNamespace(stem_pipeline_status=None, duration_seconds=300),
        SimpleNamespace(stem_pipeline_status="done", duration_seconds=200),
        SimpleNamespace(stem_pipeline_status=None, duration_seconds=500),
    ]
    count, total_sec = compute_backlog(tracks)
    assert count == 2
    assert total_sec == 800


def test_backlog_requires_confirm_above_thresholds():
    from services.audio_pipeline.migration import backlog_requires_confirm
    assert backlog_requires_confirm(15, 0) is True
    assert backlog_requires_confirm(0, 7200) is True
    assert backlog_requires_confirm(5, 100) is False


def test_stem_pipeline_status_does_not_conflict_with_computed_ui_label():
    """R-09: anderer Spaltenname als UI-Computed-Field 'stems_status' in
    media_workspace.py:1551 / ingest_service.py:280 (das ist 'Ja'/'Nein')."""
    # Spaltenname ist stem_pipeline_status, NICHT stems_status
    from services.audio_pipeline import migration
    src = open(migration.__file__, encoding="utf-8").read()
    assert "stem_pipeline_status" in src
    # Wir bauen KEINE Spalte mit dem UI-Namen 'stems_status'
    assert "ADD COLUMN stems_status" not in src
