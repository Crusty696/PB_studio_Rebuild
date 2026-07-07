"""Fixplan 2026-07-07 Schritt 6: Thumbnail-Pixmap-Cache der Timeline.

Fehlerbild (Log-Beweis Session 2026-07-07 00:55): Nach Auto-Edit-Apply wird
die Timeline neu gebaut; der ThumbnailLoadManager dedupliziert bereits
generierte Pfade (`is_done`), aber die NEUEN Clip-Items bekamen das Pixmap
nie -> Platzhalter fuer immer (`request_visible ... new_requests=0`).

Fix: TimelineView cached QPixmaps pro Datei; _register_clip_thumbnail wendet
Cache-Treffer sofort an.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage


def _qapp():
    return QApplication.instance() or QApplication([])


def _img(w: int = 32, h: int = 18) -> QImage:
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0xFF3060A0)
    return img


def _make_view():
    from ui.timeline import InteractiveTimeline as TimelineView
    return TimelineView()


def _make_clip_item(path: str, media_id: int = 1):
    from ui.timeline import TimelineClipItem, TRACK_HEIGHT
    return TimelineClipItem(
        entry_id=media_id, media_id=media_id, track_type="video",
        title="clip", x=0.0, y=0.0, width=120.0, height=TRACK_HEIGHT,
        anchors=[], thumbnail_file_path=path,
    )


def test_thumb_ready_fills_cache_and_items():
    _qapp()
    view = _make_view()
    item = _make_clip_item("C:/videos/a.mp4")
    view._register_clip_thumbnail(item)

    view._on_thumb_ready("C:/videos/a.mp4", _img())

    assert "C:/videos/a.mp4" in view._thumb_pixmaps
    assert item._thumbnail_item is not None
    assert view._thumb_loader.is_done("C:/videos/a.mp4")


def test_rebuild_items_get_cached_pixmap_immediately():
    """Kern-Regression: neues Item nach Rebuild bekommt Thumb aus Cache,
    obwohl der Loader den Pfad als done dedupliziert."""
    _qapp()
    view = _make_view()

    # Erster Build + Thumbnail fertig
    first = _make_clip_item("C:/videos/b.mp4", media_id=10)
    view._register_clip_thumbnail(first)
    view._on_thumb_ready("C:/videos/b.mp4", _img())

    # Simulierter Rebuild (Auto-Edit-Apply): Registry leeren wie im teardown
    view._thumb_items_by_path.clear()
    view._thumb_loader.reset()

    before_pix = None
    second = _make_clip_item("C:/videos/b.mp4", media_id=11)
    before_pix = second._thumbnail_item.pixmap() if second._thumbnail_item else None

    view._register_clip_thumbnail(second)

    # Ohne neuen Worker-Lauf (is_done=True) muss das Pixmap gesetzt sein
    assert view._thumb_loader.is_done("C:/videos/b.mp4")
    assert second._thumbnail_item is not None
    after_pix = second._thumbnail_item.pixmap()
    assert after_pix is not None and not after_pix.isNull()
    if before_pix is not None and not before_pix.isNull():
        assert after_pix.cacheKey() != before_pix.cacheKey()


def test_unknown_path_not_in_cache_keeps_placeholder():
    _qapp()
    view = _make_view()
    item = _make_clip_item("C:/videos/never_loaded.mp4", media_id=20)
    view._register_clip_thumbnail(item)
    assert "C:/videos/never_loaded.mp4" not in view._thumb_pixmaps
