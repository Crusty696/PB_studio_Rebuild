"""STAB-5 Controls #64-#70: ShortcutHelp-, Standardize- und StartupCheck-Dialog."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QPushButton


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _single_button(dialog: QDialog, text: str) -> QPushButton:
    buttons = [
        b for b in dialog.findChildren(QPushButton) if b.text() == text
    ]
    assert len(buttons) == 1
    button = buttons[0]
    assert button.isVisibleTo(dialog) is True
    assert button.isEnabled() is True
    return button


def test_shortcut_help_close_button_accepts() -> None:
    """Control #64: 'Schließen' akzeptiert und versteckt den Hilfedialog."""
    app = _qapp()
    from ui.dialogs.shortcut_help_dialog import ShortcutHelpDialog

    dialog = ShortcutHelpDialog()
    try:
        dialog.show()
        app.processEvents()
        button = _single_button(dialog, "Schließen")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert dialog.result() == QDialog.DialogCode.Accepted
        assert dialog.isVisible() is False
    finally:
        dialog.deleteLater()
        app.processEvents()


def test_standardize_combos_feed_selected_contract() -> None:
    """Controls #65-#67: Aufloesung/FPS/Format-Combos speisen selected()."""
    app = _qapp()
    from ui.dialogs.standardize_dialog import StandardizeVideosDialog

    dialog = StandardizeVideosDialog()
    try:
        dialog.show()
        app.processEvents()
        for combo, expected_count in (
            (dialog.convert_resolution, 4),
            (dialog.convert_fps, 5),
            (dialog.convert_format, 5),
        ):
            assert combo.isVisibleTo(dialog) is True
            assert combo.isEnabled() is True
            assert combo.count() == expected_count

        dialog.convert_resolution.setCurrentIndex(2)
        dialog.convert_fps.setCurrentIndex(1)
        dialog.convert_format.setCurrentIndex(4)
        app.processEvents()
        assert dialog.selected() == (
            "3840x2160 (4K)", "24 fps", "mp4 (Kopieren/Copy)",
        )
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def _status(**overrides):
    from services.startup_checks import SystemStatus

    return SystemStatus(**overrides)


def test_startup_check_quit_button_rejects_on_errors() -> None:
    """Control #68: 'Beenden' erscheint nur bei Fehlern und rejected."""
    app = _qapp()
    from ui.dialogs.startup_check_dialog import StartupCheckDialog

    dialog = StartupCheckDialog(_status(errors=["FFmpeg fehlt"]))
    try:
        dialog.show()
        app.processEvents()
        button = _single_button(dialog, "Beenden")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert dialog.result() == QDialog.DialogCode.Rejected
        assert dialog.isVisible() is False
    finally:
        dialog.deleteLater()
        app.processEvents()


def test_startup_check_degraded_start_button_accepts_on_errors() -> None:
    """Control #69: 'Trotzdem starten (degradierter Modus)' akzeptiert."""
    app = _qapp()
    from ui.dialogs.startup_check_dialog import StartupCheckDialog

    dialog = StartupCheckDialog(_status(errors=["FFmpeg fehlt"]))
    try:
        dialog.show()
        app.processEvents()
        button = _single_button(
            dialog, "Trotzdem starten (degradierter Modus)"
        )
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert dialog.result() == QDialog.DialogCode.Accepted
        assert dialog.isVisible() is False
    finally:
        dialog.deleteLater()
        app.processEvents()


def test_startup_check_ok_button_accepts_on_warnings_only() -> None:
    """Control #70: 'Weiter' erscheint nur ohne Fehler und akzeptiert;
    Fehler-Buttons existieren dann nicht."""
    app = _qapp()
    from ui.dialogs.startup_check_dialog import StartupCheckDialog

    dialog = StartupCheckDialog(_status(warnings=["Ollama nicht erreichbar"]))
    try:
        dialog.show()
        app.processEvents()
        texts = [b.text() for b in dialog.findChildren(QPushButton)]
        assert "Beenden" not in texts
        assert "Trotzdem starten (degradierter Modus)" not in texts
        button = _single_button(dialog, "Weiter")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert dialog.result() == QDialog.DialogCode.Accepted
        assert dialog.isVisible() is False
    finally:
        dialog.deleteLater()
        app.processEvents()
