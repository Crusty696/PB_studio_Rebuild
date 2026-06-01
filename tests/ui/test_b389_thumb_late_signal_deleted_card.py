"""B-389: spaetes Thumbnail-done-Signal darf keine geloeschte Card treffen.

Beim Rebuild quittet MediaPoolGrid laufende Thumbnail-Threads und loescht die
Cards. Ein spaet feuerndes `done`-Signal haelt eine alte Card-Referenz und
wuerde sonst `set_thumbnail()` auf einem geloeschten Qt-Objekt aufrufen.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEvent
from PySide6.QtGui import QImage


def _qapp():
    return QApplication.instance() or QApplication([])


def _img(w: int = 10, h: int = 10) -> QImage:
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0xFF202020)
    return img


def test_apply_thumbnail_ignores_deleted_card():
    app = _qapp()
    from ui.widgets.media_grid import VideoCard

    card = VideoCard(1, "t", "p.mp4")
    card.deleteLater()
    app.sendPostedEvents(card, QEvent.Type.DeferredDelete)

    # darf nicht crashen, obwohl card-C++-Objekt geloescht ist
    card.apply_thumbnail_image("p.mp4", _img())


def test_apply_thumbnail_sets_on_live_card():
    _qapp()
    from ui.widgets.media_grid import VideoCard

    card = VideoCard(2, "t", "p.mp4")
    card.apply_thumbnail_image("p.mp4", _img())

    pm = card._thumb.pixmap()
    assert pm is not None and not pm.isNull()
