"""B-710-Follow-up: ungegatetes ``error`` + Lambda-Lebensdauer.

Zwei Restbefunde der Gegenpruefung zum B-710-Fix
(``tests/ui/test_b710_preview_stream_generation.py``):

1. ``_PreviewStreamWorker.error`` blieb als EINZIGES der drei Stream-Signale
   ohne Generations-Bindung. Die Begruendung "``run()`` unterdrueckt Fehler
   nach ``stop()`` selbst" deckt nur Fehler NACH dem Seek. Ein VOR dem Seek
   emittierter Fehler liegt danach noch in der Qt-Queue und wurde weiterhin
   zugestellt: ``_on_frame_error`` -> ``setText()`` loescht die Pixmap des
   bereits laufenden NEUEN Streams, waehrend ``_is_playing`` True bleibt.

2. Die Generations-Bindung lief ueber freie Lambdas. PySide6 trennt
   Verbindungen zu GEBUNDENEN METHODEN automatisch, sobald das
   Empfaenger-C++-Objekt zerstoert wird — bei Lambdas nicht. ``frame_ready``
   feuert 15x/s, der Slot haette also nach der Zerstoerung des QLabel weiter
   gefeuert (``RuntimeError: Internal C++ object (QLabel) already deleted``).

Wie in der B-710-Datei startet ``QThread.start()`` hier nicht wirklich —
es wird nie ein ffmpeg-Prozess gespawnt, die Signale werden manuell
emittiert.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QThread

from ui.widgets import video_preview
from ui.widgets.video_preview import (
    _PREVIEW_H,
    _PREVIEW_W,
    VideoPreviewWidget,
)


class _NoStartThread(QThread):
    """QThread ohne echten Thread-Start (kein ffmpeg im Test)."""

    def start(self, *args, **kwargs):  # noqa: D102 — bewusst No-Op
        return None


def _frame_bytes() -> bytes:
    return bytes([7, 8, 9]) * (_PREVIEW_W * _PREVIEW_H)


@pytest.fixture
def widget(qapp, monkeypatch):
    monkeypatch.setattr(video_preview, "QThread", _NoStartThread)
    w = VideoPreviewWidget()
    w._current_path = "dummy.mp4"
    w._duration = 120.0
    yield w
    w._teardown_stream()


# ---------------------------------------------------------------------------
# Punkt 1 — error-Gating
# ---------------------------------------------------------------------------

def test_stale_error_does_not_wipe_the_new_streams_picture(widget):
    """Kernbeweis: ein Fehler des ABGELOESTEN Streams darf die laufende
    Wiedergabe nicht anfassen."""
    widget.play_from(0.0)
    old_worker = widget._stream_worker

    widget.seek_to(30.0)  # laufende Wiedergabe -> Stream-Neustart
    new_worker = widget._stream_worker
    assert new_worker is not old_worker

    # Der NEUE Stream liefert bereits ein Bild.
    new_worker.frame_ready.emit(_frame_bytes(), new_worker.generation)
    pm_before = widget.pixmap()
    assert pm_before is not None and not pm_before.isNull(), (
        "Vorbedingung: der neue Stream zeigt ein Bild")

    states: list[bool] = []
    widget.playback_state_changed.connect(states.append)

    # Verspaeteter Fehler des ALTEN Streams (vor dem Seek emittiert, erst
    # jetzt zugestellt).
    old_worker.error.emit("ffmpeg weg", old_worker.generation)

    pm_after = widget.pixmap()
    assert pm_after is not None and not pm_after.isNull(), (
        "stale error hat die Pixmap des laufenden Streams geloescht")
    assert widget.text() == "", (
        "stale error hat eine Fehlermeldung ueber das laufende Bild gelegt")
    assert widget._is_playing is True
    assert states == [], "kein playback_state_changed erwartet"


def test_error_of_current_stream_is_still_shown(widget):
    """Gegenprobe: der Fehler des AKTUELLEN Streams muss sichtbar bleiben."""
    widget.play_from(0.0)
    worker = widget._stream_worker

    worker.error.emit("ffmpeg nicht gefunden", worker.generation)

    assert widget.text() == "ffmpeg nicht gefunden"


# ---------------------------------------------------------------------------
# Punkt 2 — Slot-Lebensdauer nach Zerstoerung des Empfaenger-Widgets
# ---------------------------------------------------------------------------

def test_no_slot_fires_after_the_receiving_widget_is_destroyed(qapp, monkeypatch):
    """Nach Zerstoerung des QLabel darf ``frame_ready`` keinen Slot mehr
    erreichen — weder mit RuntimeError noch stillschweigend."""
    import shiboken6

    monkeypatch.setattr(video_preview, "QThread", _NoStartThread)

    seen: list[int] = []

    class _SpyPreview(VideoPreviewWidget):
        def _on_stream_frame(self, raw_data, generation):  # noqa: D102
            seen.append(generation)
            super()._on_stream_frame(raw_data, generation)

    w = _SpyPreview()
    w._current_path = "dummy.mp4"
    w._duration = 120.0
    w.play_from(0.0)
    worker = w._stream_worker
    assert worker is not None

    # Der Worker haengt bewusst an KEINEM Parent (so ist es im Produktivcode)
    # und ueberlebt das Widget.
    shiboken6.delete(w)
    assert not shiboken6.isValid(w), "Vorbedingung: C++-Objekt ist weg"

    try:
        worker.frame_ready.emit(_frame_bytes(), 0)
    except RuntimeError as exc:  # pragma: no cover — nur im ungefixten Zustand
        pytest.fail(f"Slot feuerte nach Widget-Zerstoerung: {exc}")

    assert seen == [], (
        "Slot wurde nach Zerstoerung des Empfaenger-Widgets noch aufgerufen — "
        "die Verbindung wurde nicht automatisch getrennt (freies Lambda?)"
    )
