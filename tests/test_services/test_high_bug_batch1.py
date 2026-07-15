"""B-076 + B-085 + B-087 Batch-1 regression tests.

Source-inspection-Tests, GPU+Qt-frei.
"""

from __future__ import annotations

import inspect

import pytest


# ---------------------------------------------------------------------------
# B-076: AutoEditWorker progress-Signal + progress_cb durchreichen
# ---------------------------------------------------------------------------


def test_auto_edit_worker_has_progress_signal() -> None:
    """B-076: ``AutoEditWorker`` muss ein ``progress``-Signal exponieren —
    sonst sieht der User nur "running" ueber 30-60 s."""
    from workers.edit import AutoEditWorker
    from PySide6.QtCore import Signal as _Signal  # noqa: F401

    src = inspect.getsource(AutoEditWorker)
    assert "progress = Signal(" in src, (
        "B-076: AutoEditWorker.progress = Signal(int, str) fehlt."
    )


def test_auto_edit_worker_passes_progress_cb_to_phase3() -> None:
    """B-076: ``run`` muss ``progress_cb=lambda...`` an
    ``auto_edit_phase3`` durchreichen."""
    from workers.edit import AutoEditWorker

    src = inspect.getsource(AutoEditWorker.run)
    assert "progress_cb=" in src, (
        "B-076: AutoEditWorker.run reicht progress_cb nicht durch — "
        "Service ruft progress_cb(0..100) ins Nichts."
    )
    assert "self.progress.emit" in src


# ---------------------------------------------------------------------------
# B-085: Export Disk-Space-Check vor Preprocessing
# ---------------------------------------------------------------------------


def test_export_optimized_concat_has_disk_check() -> None:
    """B-085: ``_export_optimized_concat`` muss einen
    ``shutil.disk_usage``-Check vor dem Preprocessing haben — sonst
    scheitert der Render mid-way mit "No space left on device" und
    der User verliert 30-60 Min Arbeit."""
    from services import export_service

    src = inspect.getsource(export_service._export_optimized_concat)
    # Beide Marker müssen vorhanden sein
    assert "disk_usage" in src, (
        "B-085: _export_optimized_concat braucht shutil.disk_usage-Check."
    )
    assert "RuntimeError" in src, (
        "B-085: _export_optimized_concat muss bei zu wenig Speicher "
        "RuntimeError raisen, nicht silent durchlaufen."
    )
    # Heuristik-Marker — Bytes pro Sekunde ist ein erkennbares Pattern.
    assert "bytes_per_sec" in src.lower() or "0.2" in src


# ---------------------------------------------------------------------------
# B-087: MediaPoolGrid VideoCard Thumbnail-Loader wird gerufen
# ---------------------------------------------------------------------------


def test_media_grid_loads_video_thumbnails() -> None:
    """B-087: der Card-Bau-Pfad muss ``_start_thumb_loader`` für VideoCards
    rufen — sonst bleibt jede Karte auf dem grauen ``▶``-Placeholder.

    ``_load_next_chunk`` wurde seither in ``_create_card`` (Bau einer
    einzelnen Card, inkl. Thumb-Start) und ``_build_next_chunk``
    (Chunk-Iteration) aufgeteilt — Kommentar in media_grid.py bestaetigt das
    ausdruecklich ("Bau-Code des frueheren _load_next_chunk"). Der B-087-Fix
    lebt jetzt in ``_create_card``.
    """
    from ui.widgets.media_grid import MediaPoolGrid

    src = inspect.getsource(MediaPoolGrid._create_card)
    assert "_start_thumb_loader" in src, (
        "B-087: _create_card ruft _start_thumb_loader nicht — "
        "Grid-View zeigt nur graue Placeholder statt echter Thumbs."
    )
