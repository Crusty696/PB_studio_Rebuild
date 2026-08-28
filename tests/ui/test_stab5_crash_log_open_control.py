from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_crash_log_button_click_opens_existing_log(monkeypatch, tmp_path) -> None:
    app = _qapp()
    from ui.dialogs import crash_dialog

    log_path = tmp_path / "pb_studio.log"
    log_path.write_text("crash", encoding="utf-8")
    opened: list[str] = []
    monkeypatch.setattr(crash_dialog, "_LOG_PATH", log_path)
    monkeypatch.setattr(crash_dialog.sys, "platform", "win32")
    monkeypatch.setattr(crash_dialog.os, "startfile", opened.append)

    dialog = crash_dialog.CrashDialog(RuntimeError, RuntimeError("boom"), None)
    try:
        dialog.show()
        app.processEvents()
        log_buttons = [
            button
            for button in dialog.findChildren(QPushButton)
            if button.text() == "Log-Datei öffnen"
        ]
        assert len(log_buttons) == 1
        button = log_buttons[0]
        assert button.isVisibleTo(dialog) is True
        assert button.isEnabled() is True

        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert [Path(path) for path in opened] == [log_path]
        assert dialog.isVisible() is True
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def test_crash_log_button_missing_file_shows_visible_warning(
    monkeypatch, tmp_path
) -> None:
    """B-906: Fehlen beide Logpfade, muss eine sichtbare Warnung erscheinen."""
    app = _qapp()
    from PySide6.QtWidgets import QMessageBox
    from ui.dialogs import crash_dialog

    missing = tmp_path / "does-not-exist" / "pb_studio.log"
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(crash_dialog, "_LOG_PATH", missing)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda parent, title, text, *a, **kw: warnings.append((title, text)),
    )
    opened: list[str] = []
    monkeypatch.setattr(crash_dialog.sys, "platform", "win32")
    monkeypatch.setattr(crash_dialog.os, "startfile", opened.append, raising=False)

    dialog = crash_dialog.CrashDialog(RuntimeError, RuntimeError("boom"), None)
    try:
        dialog.show()
        app.processEvents()
        button = next(
            b for b in dialog.findChildren(QPushButton)
            if b.text() == "Log-Datei öffnen"
        )
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert opened == []
        assert len(warnings) == 1
        assert str(missing) in warnings[0][1]
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def test_crash_log_button_open_failure_shows_visible_warning(
    monkeypatch, tmp_path
) -> None:
    """B-906: Fehler von os.startfile darf nicht ungefangen entkommen."""
    app = _qapp()
    from PySide6.QtWidgets import QMessageBox
    from ui.dialogs import crash_dialog

    log_path = tmp_path / "pb_studio.log"
    log_path.write_text("crash", encoding="utf-8")
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(crash_dialog, "_LOG_PATH", log_path)
    monkeypatch.setattr(crash_dialog.sys, "platform", "win32")

    def _boom(_path: str) -> None:
        raise OSError("kein Handler registriert")

    monkeypatch.setattr(crash_dialog.os, "startfile", _boom, raising=False)
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda parent, title, text, *a, **kw: warnings.append((title, text)),
    )

    dialog = crash_dialog.CrashDialog(RuntimeError, RuntimeError("boom"), None)
    try:
        dialog.show()
        app.processEvents()
        button = next(
            b for b in dialog.findChildren(QPushButton)
            if b.text() == "Log-Datei öffnen"
        )
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(warnings) == 1
        assert "kein Handler registriert" in warnings[0][1]
        assert dialog.isVisible() is True
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def test_crash_dialog_close_button_accepts_and_hides(monkeypatch) -> None:
    """STAB-5 Control #27: Schliessen-Button ist einzig, sichtbar, aktiv und
    schliesst den Dialog ueber accept()."""
    app = _qapp()
    from ui.dialogs import crash_dialog
    from PySide6.QtWidgets import QDialog

    dialog = crash_dialog.CrashDialog(RuntimeError, RuntimeError("boom"), None)
    try:
        dialog.show()
        app.processEvents()
        close_buttons = [
            b for b in dialog.findChildren(QPushButton)
            if b.text() == "Schliessen"
        ]
        assert len(close_buttons) == 1
        button = close_buttons[0]
        assert button.isVisibleTo(dialog) is True
        assert button.isEnabled() is True

        accepted: list[bool] = []
        dialog.accepted.connect(lambda: accepted.append(True))
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert accepted == [True]
        assert dialog.result() == QDialog.DialogCode.Accepted
        assert dialog.isVisible() is False
    finally:
        dialog.deleteLater()
        app.processEvents()
