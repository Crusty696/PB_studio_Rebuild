"""B-605 / B-643: Thumbnail-Jobs muessen den Tod der Timeline ueberleben.

Crash-Signatur B-605 (CrashDump 2026-07-08 05:45, cdb !analyze -v):
NULL_CLASS_PTR_WRITE in Qt6Core — QThread::start -> QThread::finished ->
qt_static_metacall, KEIN Python-Frame im Crash-Thread. Ursache: der einzige
GC-Schutz (self._thumb_threads) und Cleanup-Pfad hingen am Timeline-Widget;
wurde es beim Workspace-/Projekt-Wechsel zerstoert waehrend ffmpeg-Thumb-
Threads liefen, zerstoerte Python-GC den C++-QThread im Lauf.

B-643 (2026-07-15): Der QThread-je-Thumbnail-Pfad wurde durch den geteilten
QThreadPool aus media_grid ersetzt (B-508-Muster, dort laengst produktiv).
Grund: ``_extract_thumb_qimage`` hat einen Disk-Cache -> bei Cache-Treffern
sind die Jobs sofort fertig und der Loader erzeugte ~30 native Threads pro
Sekunde. Dieser Thread-Churn ist der Hauptverdacht fuer den AppHang
(GIL-Halt in nativem Qt-Code, sogar der Watchdog-Thread verstummte).

Die B-605-INVARIANTE bleibt und wird hier weiter geprueft — sie ist jetzt
strukturell erfuellt statt handverdrahtet: Der Pool besitzt die Threads
C++-seitig und ``setAutoDelete(True)`` laesst ihn das Runnable nach run()
abraeumen. Es existiert kein Python-QThread-Wrapper mehr, dessen GC einen
laufenden Thread zerstoeren koennte.

Geprueft:
1. Kein QThread-je-Thumbnail mehr; der Job geht in den Pool.
2. Kein widget-gebundener quit/wait-Cleanup-Slot.
3. ``done`` feuert IMMER — sonst bliebe der inflight-Slot des
   ThumbnailLoadManager (max_concurrent=2) fuer immer belegt.
4. Funktional: Timeline stirbt waehrend der Job laeuft -> kein Crash,
   der Pool bringt den Job sauber zu Ende.
"""
from __future__ import annotations

import inspect
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


def test_thumb_worker_uses_shared_pool_not_own_qthread():
    """B-643: kein eigener QThread je Thumbnail mehr, sondern der geteilte Pool."""
    from ui.timeline import InteractiveTimeline

    src = inspect.getsource(InteractiveTimeline._start_thumb_worker)
    # Gepoolter Pfad (B-508-Muster aus media_grid wiederverwendet):
    assert "_get_thumb_pool()" in src
    assert "_TimelineThumbRunnable" in src
    # Der Thread-Churn-Pfad ist weg:
    assert "QThread()" not in src, "B-643: kein QThread je Thumbnail mehr"
    assert "moveToThread" not in src
    assert "self._thumb_threads" not in src
    # Faellt der Start aus, muss der inflight-Slot freigegeben werden, sonst
    # startet der Loader nie wieder einen Job fuer diesen Pfad.
    assert "self._thumb_loader.on_done(file_path)" in src


def test_thumb_runnable_always_emits_done():
    """Der Loader gibt den inflight-Slot NUR in on_done() frei.

    Bliebe ``done`` bei einem ffmpeg-/Extract-Fehler aus, waeren die 2
    Cap-Plaetze dauerhaft belegt und die Timeline zeigte nie wieder ein
    Thumbnail. Der Emit muss deshalb hinter dem except liegen, nicht darin.
    """
    from ui.timeline import _TimelineThumbRunnable

    src = inspect.getsource(_TimelineThumbRunnable.run)
    assert "except Exception" in src
    assert "img = QImage()" in src, "Fehlerfall muss ein leeres Bild liefern"
    assert "self._signals.done.emit" in src


def test_signal_holder_lives_on_the_view_not_the_runnable():
    """Der Holder muss den einzelnen Job ueberleben.

    Haenge er am Runnable (wie in media_grid, wo kein Cap dranhaengt), koennte
    er nach run() per autoDelete/GC verschwinden BEVOR das
    QueuedConnection-Event zugestellt ist — Qt verwirft pending Events eines
    zerstoerten Senders. ``done`` bliebe aus -> inflight-Slot fuer immer belegt.
    """
    from ui.timeline import InteractiveTimeline

    src = inspect.getsource(InteractiveTimeline.__init__)
    assert "self._thumb_signals = _TimelineThumbSignals()" in src
    assert "self._thumb_signals.done.connect" in src


def test_no_widget_bound_thumb_cleanup_slot_left():
    from ui import timeline as tl

    assert not hasattr(tl.InteractiveTimeline, "_on_thumb_worker_done"), (
        "B-605: der widget-gebundene quit/wait-Cleanup-Slot muss ersetzt sein"
    )


def test_thumb_job_survives_timeline_destruction(monkeypatch):
    """B-605-Invariante, jetzt gepoolt: Timeline zerstoeren, waehrend der Job
    laeuft -> kein Crash, der Pool bringt ihn sauber zu Ende."""
    from ui import timeline as tl
    from ui.widgets import media_grid as mg

    app = _qapp()

    # Extraktion kuenstlich verlangsamen (simuliert laufenden ffmpeg-Lauf).
    # _TimelineThumbRunnable.run() importiert die Funktion zur Laufzeit aus dem
    # Modul -> der Patch greift.
    def _slow_extract(file_path, w, h):
        time.sleep(0.35)
        from PySide6.QtGui import QImage
        return QImage()

    monkeypatch.setattr(mg, "_extract_thumb_qimage", _slow_extract)

    timeline = tl.InteractiveTimeline()
    timeline._start_thumb_worker("X:/nicht/vorhanden/b605_test.mp4")

    # Timeline sofort zerstoeren, waehrend der Pool-Job noch schlaeft —
    # exakt das Crash-Szenario (Workspace-Wechsel bei laufenden Thumbs).
    timeline.deleteLater()
    del timeline
    app.processEvents()

    # Der Pool muss den Job zu Ende bringen, ohne dass etwas nativ crasht.
    pool = mg._get_thumb_pool()
    assert pool.waitForDone(5000), (
        "B-643: Thumbnail-Job im Pool wurde nach Widget-Tod nicht fertig"
    )
    app.processEvents()
