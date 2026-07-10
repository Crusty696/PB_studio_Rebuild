"""B-605: Thumbnail-QThreads muessen den Tod der Timeline ueberleben.

Crash-Signatur (CrashDump 2026-07-08 05:45, cdb !analyze -v):
NULL_CLASS_PTR_WRITE in Qt6Core — QThread::start -> QThread::finished ->
qt_static_metacall, KEIN Python-Frame im Crash-Thread. Ursache: der einzige
GC-Schutz (self._thumb_threads) und Cleanup-Pfad hingen am Timeline-Widget;
wurde es beim Workspace-/Projekt-Wechsel zerstoert waehrend ffmpeg-Thumb-
Threads liefen, zerstoerte Python-GC den C++-QThread im Lauf.

Fix-Invarianten (source-level + funktional):
1. Beendigungs-Kette widget-unabhaengig: worker.done -> thread.quit,
   thread.finished -> deleteLater + modul-globale Registry-Freigabe.
2. Kein Widget-gebundener quit/wait-Cleanup-Slot mehr.
3. Funktional: Timeline stirbt waehrend Worker laeuft -> kein Crash,
   Thread beendet sich, Registry leert sich.
"""
from __future__ import annotations

import inspect
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


def test_thumb_worker_wiring_is_widget_independent():
    from ui.timeline import InteractiveTimeline

    src = inspect.getsource(InteractiveTimeline._start_thumb_worker)
    # Beendigung haengt an worker/thread selbst, nicht am Widget:
    assert "worker.done.connect(thread.quit)" in src
    assert "thread.finished.connect(worker.deleteLater)" in src
    assert "thread.finished.connect(thread.deleteLater)" in src
    # GC-Schutz modul-global, nicht widget-gebunden:
    assert "_ACTIVE_THUMB_THREADS.append" in src
    assert "self._thumb_threads" not in src
    # Registry-Freigabe ohne self-Capture (functools.partial, kein lambda self):
    assert "functools.partial(_release_thumb_pair" in src


def test_no_widget_bound_thumb_cleanup_slot_left():
    from ui import timeline as tl

    assert not hasattr(tl.InteractiveTimeline, "_on_thumb_worker_done"), (
        "B-605: der widget-gebundene quit/wait-Cleanup-Slot muss ersetzt sein"
    )
    assert hasattr(tl, "_ACTIVE_THUMB_THREADS")
    assert hasattr(tl, "_release_thumb_pair")


def test_thumb_thread_survives_timeline_destruction(monkeypatch):
    """Timeline zerstoeren, waehrend der Thumb-Worker noch laeuft -> kein
    Crash, Thread beendet sich selbst, globale Registry leert sich."""
    from ui import timeline as tl
    from ui.widgets import media_grid as mg

    app = _qapp()

    # _extract kuenstlich verlangsamen (simuliert laufenden ffmpeg-Lauf).
    def _slow_extract(self):
        time.sleep(0.35)
        from PySide6.QtGui import QImage
        return QImage()

    monkeypatch.setattr(mg._ThumbWorker, "_extract", _slow_extract)

    timeline = tl.InteractiveTimeline()
    before = len(tl._ACTIVE_THUMB_THREADS)
    timeline._start_thumb_worker("X:/nicht/vorhanden/b605_test.mp4")
    assert len(tl._ACTIVE_THUMB_THREADS) == before + 1

    # Timeline sofort zerstoeren, waehrend der Worker-Thread noch schlaeft —
    # exakt das Crash-Szenario (Workspace-Wechsel bei laufenden Thumbs).
    timeline.deleteLater()
    del timeline
    app.processEvents()

    # Thread muss sich selbst beenden und aus der Registry austragen.
    deadline = time.time() + 5.0
    while time.time() < deadline and len(tl._ACTIVE_THUMB_THREADS) > before:
        app.processEvents()
        time.sleep(0.02)

    assert len(tl._ACTIVE_THUMB_THREADS) == before, (
        "B-605: Thumb-Thread hat sich nach Widget-Tod nicht selbst aufgeraeumt"
    )
