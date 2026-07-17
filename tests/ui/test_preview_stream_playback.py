"""Persistenter ffmpeg-Wiedergabe-Stream der Video-Vorschau (User 2026-07-17).

Vorher: Play startete pro 100ms-Tick einen NEUEN ffmpeg-Prozess
(Spawn+Seek+Decode pro Frame) -> Stottern. Jetzt: EIN ffmpeg mit -re
(Echtzeit-Pacing) streamt rawvideo in eine Pipe; ein Leser-Thread liefert
fertige Frames.

- Echt-Test: Worker liefert aus einer realen Fixture >=2 korrekte Frames.
- Source-Pins: Play nutzt den Stream-Worker (kein Timer-Frame-Extract mehr);
  Teardown parkt laufende Threads B-652-sicher (kein Referenz-Drop auf
  laufende QThreads).
"""
from __future__ import annotations

import inspect
import time
from pathlib import Path

import pytest

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "clips_20" / (
    "clip_01_20250719_0337_Enchanted_Bioluminescent_Jungle_v1.mp4")


@pytest.mark.skipif(not _FIXTURE.exists(), reason="Fixture-Clip fehlt")
def test_stream_worker_delivers_real_frames():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])

    from ui.widgets.video_preview import (
        _PreviewStreamWorker, _PREVIEW_W, _PREVIEW_H)

    frames: list[int] = []
    worker = _PreviewStreamWorker(str(_FIXTURE), 0.0)
    worker.frame_ready.connect(lambda b: frames.append(len(b)),
                               type=__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.ConnectionType.DirectConnection)

    import threading
    t = threading.Thread(target=worker.run, daemon=True)
    t.start()
    deadline = time.time() + 15
    while len(frames) < 2 and time.time() < deadline:
        time.sleep(0.05)
    worker.stop()
    t.join(timeout=5)

    assert len(frames) >= 2, "Stream muss mehrere Frames liefern"
    assert all(n == _PREVIEW_W * _PREVIEW_H * 3 for n in frames), (
        "jeder Frame muss exakt W*H*3 Bytes gross sein")


def test_play_uses_persistent_stream_not_per_frame_processes():
    from ui.widgets.video_preview import VideoPreviewWidget

    src = inspect.getsource(VideoPreviewWidget.play_from)
    assert "_PreviewStreamWorker" in src, (
        "Play muss den persistenten Stream nutzen (kein Timer-Extract)")
    assert "_play_timer" not in inspect.getsource(VideoPreviewWidget), (
        "der alte 100ms-Frame-Extract-Timer darf nicht zurueckkommen")


def test_stream_teardown_is_b652_safe():
    """Kein Referenz-Drop auf laufende QThreads (B-652-Muster)."""
    from ui.widgets.video_preview import VideoPreviewWidget

    src = inspect.getsource(VideoPreviewWidget._teardown_stream)
    assert "_dying_stream_threads.append" in src
    assert "isRunning()" in src


def test_stream_worker_uses_realtime_pacing():
    from ui.widgets.video_preview import _PreviewStreamWorker

    src = inspect.getsource(_PreviewStreamWorker.run)
    assert '"-re"' in src, "-re noetig: ffmpeg muss die Ausgabe in Echtzeit takten"
    assert "rawvideo" in src
