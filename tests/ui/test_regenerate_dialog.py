"""Phase 06 / Task 6.3: Confirm-Dialog ``confirm_regenerate``."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox

from ui.workspaces.schnitt.regenerate_dialog import confirm_regenerate


def _qapp():
    return QApplication.instance() or QApplication([])


def test_yes_returns_true():
    _qapp()
    with patch.object(
        QMessageBox, "warning",
        return_value=QMessageBox.StandardButton.Yes,
    ):
        assert confirm_regenerate(None) is True


def test_no_returns_false():
    _qapp()
    with patch.object(
        QMessageBox, "warning",
        return_value=QMessageBox.StandardButton.No,
    ):
        assert confirm_regenerate(None) is False


# ---------------------------------------------------------------------------
# T5.10 Coverage-Sweep (E10)
# ---------------------------------------------------------------------------


def test_default_button_is_no():
    """Verifikation: confirm_regenerate ruft QMessageBox.warning mit
    StandardButton.No als Default-Button auf — User muss explizit Yes klicken.

    Test-Strategie: Wir mocken QMessageBox.warning und inspizieren die Args.
    """
    _qapp()
    captured = {}

    def _fake_warning(parent, title, text, buttons, default_button):
        captured["buttons"] = buttons
        captured["default_button"] = default_button
        # Simuliere "kein Klick / Default zurueck" — wir liefern den Default
        # zurueck. Effekt: confirm_regenerate liefert False.
        return default_button

    with patch.object(QMessageBox, "warning", side_effect=_fake_warning):
        result = confirm_regenerate(None)

    assert captured["default_button"] == QMessageBox.StandardButton.No
    assert result is False
    # Buttons-Set: Yes | No
    assert captured["buttons"] == (
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
