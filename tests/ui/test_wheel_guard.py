"""WheelGuard Tests — SCHNITT Redesign 2026-05-09 Task 3.1."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt, QPoint, QPointF, QEvent
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QComboBox, QDoubleSpinBox, QPushButton, QSlider, QSpinBox

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


# ---------------------------------------------------------------------------
# T5.3 Coverage-Sweep (E3)
# ---------------------------------------------------------------------------


def test_doublespinbox_unfocused_blocks_wheel():
    app = _qapp()
    guard = WheelGuard(app)
    app.installEventFilter(guard)

    sb = QDoubleSpinBox()
    sb.setRange(0.0, 100.0)
    sb.setSingleStep(1.0)
    sb.setValue(50.0)
    sb.show()
    sb.clearFocus()
    QApplication.sendEvent(sb, _wheel(sb, delta=-120))
    assert sb.value() == 50.0


def test_pushbutton_passes_through():
    """Negativtest: QPushButton ist nicht in _GUARDED_TYPES → Event ungehindert."""
    app = _qapp()
    guard = WheelGuard(app)
    app.installEventFilter(guard)

    btn = QPushButton("x")
    btn.show()
    btn.clearFocus()
    # Event darf den Filter passieren — kein RaiseError, returnvalue von filter ist False.
    # Wir verifizieren: WheelGuard.eventFilter() liefert False (super delegiert) für Buttons.
    fake_evt = _wheel(btn)
    result = guard.eventFilter(btn, fake_evt)
    assert result is False
