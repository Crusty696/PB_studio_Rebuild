"""B-710: Seek waehrend der Wiedergabe darf den neuen Stream nicht killen.

Befund:
1. `play_from()` verbindet `thread.finished` mit `_on_stream_thread_finished`.
   Nach einem Seek (der `play_from()` erneut aufruft) trifft das `finished`
   des ALTEN Threads verspaetet ein — der Slot sah `_stream_thread is not
   None` + `_is_playing` und riss per `_teardown_stream()` den bereits
   gestarteten NEUEN Stream ab.
2. `_on_stream_frame()` pruefte nur `_stream_worker is not None` und
   `_is_playing`. Frames des alten Streams, die noch in der Event-Queue
   lagen, wurden angezeigt und zaehlten `_stream_frames`/`_current_time`
   hoch -> falsche Positionsanzeige.

Fix: Stream-Generation. `_teardown_stream()` erhoeht sie, Slots verwerfen
Signale fremder Generation.

Die Tests starten KEINEN echten Thread (QThread.start() ist in der
Test-Subklasse ein No-Op) — es wird also nie ein ffmpeg-Prozess gespawnt.
Die Signale des alten Streams werden manuell emittiert, exakt so wie Qt sie
verspaetet zustellen wuerde.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QThread

from ui.widgets import video_preview
from ui.widgets.video_preview import (
    _PREVIEW_FPS,
    _PREVIEW_H,
    _PREVIEW_W,
    VideoPreviewWidget,
)


class _NoStartThread(QThread):
    """QThread ohne echten Thread-Start (kein ffmpeg im Test)."""

    def start(self, *args, **kwargs):  # noqa: D102 — bewusst No-Op
        return None


@pytest.fixture
def widget(qapp, monkeypatch):
    monkeypatch.setattr(video_preview, "QThread", _NoStartThread)
    w = VideoPreviewWidget()
    w._current_path = "dummy.mp4"
    w._duration = 120.0
    yield w
    w._teardown_stream()


def _frame_bytes() -> bytes:
    return bytes([7, 8, 9]) * (_PREVIEW_W * _PREVIEW_H)


def test_old_stream_finished_does_not_stop_new_stream(widget):
    widget.play_from(0.0)
    old_thread = widget._stream_thread

    widget.seek_to(30.0)  # laufende Wiedergabe -> Stream-Neustart
    new_worker = widget._stream_worker
    new_thread = widget._stream_thread
    assert new_thread is not old_thread

    states: list[bool] = []
    widget.playback_state_changed.connect(states.append)

    # Verspaetetes finished des ALTEN Threads
    old_thread.finished.emit()
    QCoreApplication.processEvents()

    assert widget._is_playing is True, (
        "finished des alten Streams darf die Wiedergabe nicht beenden")
    assert widget._stream_worker is new_worker, "neuer Worker wurde abgeraeumt"
    assert widget._stream_thread is new_thread, "neuer Thread wurde abgeraeumt"
    assert states == [], "kein playback_state_changed(False) erwartet"


def test_stale_frame_of_old_stream_is_ignored(widget):
    widget.play_from(0.0)
    old_worker = widget._stream_worker

    widget.seek_to(30.0)
    assert widget._stream_frames == 0
    assert widget._current_time == pytest.approx(30.0)

    positions: list[float] = []
    widget.position_changed.connect(lambda cur, tot: positions.append(cur))

    # Follow-up 2026-07-27: die Generation reist jetzt IM Signal mit (statt in
    # einer Lambda-Closure). Der stale Frame traegt damit weiterhin genau die
    # alte Generation — die Aussage des Tests ist unveraendert.
    old_worker.frame_ready.emit(_frame_bytes(), old_worker.generation)  # stale

    assert widget._stream_frames == 0, "stale Frame darf nicht mitzaehlen"
    assert widget._current_time == pytest.approx(30.0), (
        "stale Frame darf die Position nicht verschieben")
    assert positions == [], "stale Frame darf keine Position melden"
    pm = widget.pixmap()
    assert pm is None or pm.isNull(), "stale Frame darf nicht angezeigt werden"


def test_current_stream_frame_still_displayed(widget):
    """Gegenprobe: Frames der AKTUELLEN Generation kommen weiter durch."""
    widget.play_from(10.0)
    worker = widget._stream_worker

    worker.frame_ready.emit(_frame_bytes(), worker.generation)

    assert widget._stream_frames == 1
    assert widget._current_time == pytest.approx(10.0 + 1 / _PREVIEW_FPS)
    pm = widget.pixmap()
    assert pm is not None and not pm.isNull()
    assert (pm.width(), pm.height()) == (_PREVIEW_W, _PREVIEW_H)


def test_eof_of_current_stream_still_stops_playback(widget):
    """Gegenprobe: EOF des aktuellen Streams beendet die Wiedergabe weiterhin."""
    widget.play_from(0.0)
    thread = widget._stream_thread

    states: list[bool] = []
    widget.playback_state_changed.connect(states.append)

    thread.finished.emit()
    QCoreApplication.processEvents()

    assert widget._is_playing is False
    assert states == [False]
