"""B-388: Media-Grid-Thumbnail-Worker darf kein QPixmap im Worker-Thread bauen.

QPixmap ist eine GUI-Ressource und gehoert in den GUI-Thread. Der
``_ThumbWorker`` laeuft in einem QThread und muss daher ein thread-sicheres
``QImage`` liefern; die Umwandlung in ein QPixmap erfolgt im GUI-Thread-Slot.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPixmap


def _qapp():
    return QApplication.instance() or QApplication([])


def test_thumb_worker_extract_returns_qimage_not_qpixmap():
    _qapp()
    from ui.widgets.media_grid import _ThumbWorker

    worker = _ThumbWorker("does_not_exist_xyz.mp4", 80, 45)
    result = worker._extract()  # fehlender Pfad → Placeholder

    assert isinstance(result, QImage)
    assert not isinstance(result, QPixmap)
    assert result.width() == 80 and result.height() == 45


def test_placeholder_image_is_qimage():
    _qapp()
    from ui.widgets.media_grid import _placeholder_image

    img = _placeholder_image(80, 45, "X")
    assert isinstance(img, QImage)
    assert img.width() == 80 and img.height() == 45
