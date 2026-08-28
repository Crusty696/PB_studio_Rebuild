"""STAB-5 Controls #28-#31: GpuRecoveryDialog-Buttons elementgenau belegen."""

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


def _make_dialog():
    from ui.dialogs.gpu_recovery_dialog import GpuRecoveryDialog

    dialog = GpuRecoveryDialog()
    dialog.show()
    QApplication.processEvents()
    assert dialog.choice() == "cancel"
    return dialog


def test_recheck_button_sets_choice_and_accepts() -> None:
    """Control #28: 'GPU erneut pruefen' -> choice 'recheck' + accept."""
    app = _qapp()
    dialog = _make_dialog()
    try:
        button = _single_button(dialog, "\U0001F504 GPU erneut pruefen")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert dialog.choice() == "recheck"
        assert dialog.result() == QDialog.DialogCode.Accepted
        assert dialog.isVisible() is False
    finally:
        dialog.deleteLater()
        app.processEvents()


def test_restart_button_sets_choice_and_accepts() -> None:
    """Control #29: 'PB Studio beenden (Reboot)' -> choice 'restart' + accept."""
    app = _qapp()
    dialog = _make_dialog()
    try:
        button = _single_button(dialog, "PB Studio beenden (Reboot)")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert dialog.choice() == "restart"
        assert dialog.result() == QDialog.DialogCode.Accepted
        assert dialog.isVisible() is False
    finally:
        dialog.deleteLater()
        app.processEvents()


def test_cpu_button_sets_choice_env_flag_and_accepts(monkeypatch) -> None:
    """Control #30: CPU-Fallback -> choice 'cpu_fallback', Env-Flag, accept."""
    app = _qapp()
    monkeypatch.delenv("PB_STUDIO_FORCE_CPU", raising=False)
    dialog = _make_dialog()
    try:
        button = _single_button(dialog, "⏵ Mit CPU starten — langsamer")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert dialog.choice() == "cpu_fallback"
        assert os.environ.get("PB_STUDIO_FORCE_CPU") == "1"
        assert dialog.result() == QDialog.DialogCode.Accepted
        assert dialog.isVisible() is False
    finally:
        monkeypatch.delenv("PB_STUDIO_FORCE_CPU", raising=False)
        dialog.deleteLater()
        app.processEvents()


def test_cancel_button_keeps_choice_cancel_and_rejects() -> None:
    """Control #31: 'Abbrechen' -> choice 'cancel' + reject, kein Env-Flag."""
    app = _qapp()
    dialog = _make_dialog()
    try:
        button = _single_button(dialog, "Abbrechen")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert dialog.choice() == "cancel"
        assert dialog.result() == QDialog.DialogCode.Rejected
        assert dialog.isVisible() is False
    finally:
        dialog.deleteLater()
        app.processEvents()
