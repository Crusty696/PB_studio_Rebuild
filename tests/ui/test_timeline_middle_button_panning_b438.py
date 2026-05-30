"""B-438 Regressionstest: InteractiveTimeline hatte ZWEI mousePressEvent-
Definitionen — die spätere (nur Fokus) überschrieb die frühere (Panning),
wodurch Mittlere-Maustaste-Panning tot war. Nach dem Merge muss ein
Middle-Button-Press wieder ``_panning`` aktivieren UND Fokus setzen.

Dieser Test würde VOR dem Fix fehlschlagen (``_panning`` bliebe False).
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPointF, QEvent
from PySide6.QtGui import QMouseEvent


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _mouse(evt_type, button):
    pos = QPointF(10.0, 10.0)
    return QMouseEvent(evt_type, pos, pos, button, button,
                       Qt.KeyboardModifier.NoModifier)


def test_middle_button_starts_panning_b438(qapp):
    from ui.timeline import InteractiveTimeline
    tl = InteractiveTimeline()
    try:
        assert tl._panning is False
        # Mittlere Maustaste -> Panning muss starten (war vor Merge tot)
        tl.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress,
                                  Qt.MouseButton.MiddleButton))
        assert tl._panning is True, "B-438: Middle-Button-Panning inaktiv"
        # Release beendet Panning sauber
        tl.mouseReleaseEvent(_mouse(QEvent.Type.MouseButtonRelease,
                                    Qt.MouseButton.MiddleButton))
        assert tl._panning is False
    finally:
        tl.deleteLater()


def test_left_button_does_not_pan_but_keeps_focus_path(qapp):
    from ui.timeline import InteractiveTimeline
    tl = InteractiveTimeline()
    try:
        # Linke Maustaste darf KEIN Panning auslösen (Fokus/Selektion-Pfad)
        tl.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress,
                                  Qt.MouseButton.LeftButton))
        assert tl._panning is False
    finally:
        tl.deleteLater()


def test_only_one_mousepresshandler_defined_b438():
    """Strukturgarantie: genau EINE mousePressEvent-Definition in der Klasse."""
    import inspect
    from ui.timeline import InteractiveTimeline
    src = inspect.getsource(InteractiveTimeline)
    assert src.count("def mousePressEvent") == 1, \
        "B-438: doppelte mousePressEvent-Definition zurückgekehrt"
