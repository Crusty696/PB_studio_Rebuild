from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeyEvent

from ui.shortcut_manager import ShortcutManager, _event_int


def test_b329_event_int_accepts_pyside6_keyboard_modifier_enum() -> None:
    event = QKeyEvent(
        QEvent.Type.KeyPress,
        Qt.Key.Key_A,
        Qt.KeyboardModifier.NoModifier,
    )

    assert _event_int(event) == int(Qt.Key.Key_A)


def test_b329_shortcut_manager_matches_plain_key_without_crash() -> None:
    manager = ShortcutManager()
    manager.reset_to_defaults()
    event = QKeyEvent(
        QEvent.Type.KeyPress,
        Qt.Key.Key_Space,
        Qt.KeyboardModifier.NoModifier,
    )

    assert manager.matches("play_pause", event) is True
