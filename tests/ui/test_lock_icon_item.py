"""LockIconItem Tests — SCHNITT Redesign 2026-05-09 Task 3.2."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QGraphicsScene
from PySide6.QtCore import QPointF, QRectF
from ui.widgets.lock_icon_item import LockIconItem


def _qapp():
    return QApplication.instance() or QApplication([])


def test_initial_state_unlocked():
    _qapp()
    item = LockIconItem(parent_width=200, parent_height=40)
    assert item.is_locked is False


def test_set_locked_changes_visual():
    _qapp()
    item = LockIconItem(parent_width=200, parent_height=40)
    initial_color = item.brush().color().rgba()
    item.set_locked(True)
    assert item.is_locked is True
    assert item.brush().color().rgba() != initial_color


def test_position_top_right():
    _qapp()
    item = LockIconItem(parent_width=200, parent_height=40)
    pos = item.pos()
    assert pos.x() > 180  # rechtsbuendig
    assert pos.y() < 5    # oben


# ---------------------------------------------------------------------------
# T5.4 Coverage-Sweep (E4)
# ---------------------------------------------------------------------------


def test_toggle_true_false_true_visual():
    """Brush-Color-Roundtrip: True → False → True landet wieder bei Locked-Farbe."""
    _qapp()
    item = LockIconItem(parent_width=200, parent_height=40)

    color_unlocked = item.brush().color().rgba()
    item.set_locked(True)
    color_locked = item.brush().color().rgba()
    item.set_locked(False)
    color_unlocked2 = item.brush().color().rgba()
    item.set_locked(True)
    color_locked2 = item.brush().color().rgba()

    assert color_unlocked != color_locked
    assert color_unlocked == color_unlocked2
    assert color_locked == color_locked2
