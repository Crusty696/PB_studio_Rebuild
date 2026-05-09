"""LockIconItem — visualer State auf TimelineClipItems.
Klick togglet `locked`-Flag; Toggle wird vom Parent-Clip via
mouse-press abgefangen und in QUndoStack gepusht."""
from PySide6.QtCore import QRectF
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import QGraphicsRectItem


_SIZE = 12


class LockIconItem(QGraphicsRectItem):
    UNLOCKED_COLOR = QColor(255, 255, 255, 100)
    LOCKED_COLOR = QColor(255, 215, 70, 230)

    def __init__(self, parent_width: float, parent_height: float, parent=None):
        super().__init__(QRectF(0, 0, _SIZE, _SIZE), parent)
        self.is_locked: bool = False
        # rechte obere Ecke, 4 px Innenabstand
        self.setPos(parent_width - _SIZE - 4, 2)
        self.setZValue(15)
        self.setPen(QPen(QColor(0, 0, 0, 180), 1))
        self.setBrush(QBrush(self.UNLOCKED_COLOR))
        self.setAcceptHoverEvents(True)
        self.setToolTip("Clip sperren / entsperren — gesperrte Clips bleiben bei Re-Generate erhalten")

    def set_locked(self, locked: bool) -> None:
        self.is_locked = locked
        self.setBrush(QBrush(self.LOCKED_COLOR if locked else self.UNLOCKED_COLOR))
