"""Application-weiter EventFilter: blockiert Wheel-Events auf
QComboBox/QSlider/QSpinBox/QDoubleSpinBox solange das Widget keinen Fokus hat.
Verhindert versehentliches Verstellen beim Mausrad-Drueberscrollen."""
from PySide6.QtCore import QObject, QEvent
from PySide6.QtWidgets import QComboBox, QSlider, QSpinBox, QDoubleSpinBox


_GUARDED_TYPES = (QComboBox, QSlider, QSpinBox, QDoubleSpinBox)


class WheelGuard(QObject):
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Wheel and isinstance(obj, _GUARDED_TYPES):
            if not obj.hasFocus():
                event.ignore()
                return True
        return super().eventFilter(obj, event)
