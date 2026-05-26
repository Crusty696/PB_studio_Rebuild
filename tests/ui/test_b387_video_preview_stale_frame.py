"""B-387: VideoPreview darf kein veraltetes Frame eines frueheren Videos zeigen.

Befund: `_on_frame_ready()` setzt die Pixmap ohne zu pruefen, fuer welchen Pfad
das Frame erzeugt wurde. Ein spaet eintreffendes Frame von Video A kann die
bereits auf Video B umgeschaltete Preview ueberschreiben.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ui.widgets.video_preview import VideoPreviewWidget


def _qapp():
    return QApplication.instance() or QApplication([])


def _rgb_bytes(w: int, h: int) -> bytes:
    return bytes([10, 20, 30]) * (w * h)


def test_on_frame_ready_discards_stale_frame_from_previous_video():
    _qapp()
    w = VideoPreviewWidget()
    w._current_path = "B.mp4"
    w._active_request_path = "A.mp4"  # Frame stammt vom alten Pfad

    w._on_frame_ready(_rgb_bytes(2, 2), 2, 2)

    pm = w.pixmap()
    assert pm is None or pm.isNull(), "Stale Frame vom alten Video darf nicht gezeigt werden"


def test_on_frame_ready_shows_current_frame():
    _qapp()
    w = VideoPreviewWidget()
    w._current_path = "B.mp4"
    w._active_request_path = "B.mp4"

    w._on_frame_ready(_rgb_bytes(2, 2), 2, 2)

    pm = w.pixmap()
    assert pm is not None and not pm.isNull(), "Aktuelles Frame muss angezeigt werden"
