"""WheelGuard Tests — SCHNITT Redesign 2026-05-09 Task 3.1."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt, QPoint, QPointF, QEvent
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QComboBox, QSlider, QSpinBox

from ui.widgets.wheel_guard import WheelGuard


def _qapp():
    return QApplication.instance() or QApplication([])


def _wheel(widget, delta=120):
    return QWheelEvent(
        QPointF(10.0, 10.0), widget.mapToGlobal(QPoint(10, 10)),
        QPoint(0, 0), QPoint(0, delta),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )


def test_combo_unfocused_blocks_wheel():
    app = _qapp()
    guard = WheelGuard(app)
    app.installEventFilter(guard)

    cb = QComboBox()
    cb.addItems(["a", "b", "c"])
    cb.setCurrentIndex(0)
    cb.show()
    cb.clearFocus()
    QApplication.sendEvent(cb, _wheel(cb))
    assert cb.currentIndex() == 0


def test_slider_focused_passes_wheel():
    app = _qapp()
    guard = WheelGuard(app)
    app.installEventFilter(guard)

    sl = QSlider(Qt.Orientation.Horizontal)
    sl.setRange(0, 100)
    sl.setValue(50)
    sl.show()
    sl.activateWindow()
    sl.setFocus(Qt.FocusReason.OtherFocusReason)
    app.processEvents()
    assert sl.hasFocus()
    QApplication.sendEvent(sl, _wheel(sl, delta=120))
    assert sl.value() != 50


def test_spinbox_unfocused_blocks_wheel():
    app = _qapp()
    guard = WheelGuard(app)
    app.installEventFilter(guard)

    sb = QSpinBox()
    sb.setRange(0, 100)
    sb.setValue(50)
    sb.show()
    sb.clearFocus()
    QApplication.sendEvent(sb, _wheel(sb, delta=-120))
    assert sb.value() == 50
