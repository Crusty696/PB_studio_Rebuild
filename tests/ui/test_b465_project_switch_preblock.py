"""B-465: Sichtbarer Pre-Block bei Projekt-Oeffnen/-Erstellen waehrend laufender Tasks.

Frueher oeffnete sich der Projekt-Oeffnen/-Erstellen-Dialog sofort und der Block
erschien erst nach Bestaetigung tief im Worker (B-050-Fehler). Fix: ein
Pre-Block warnt sofort und bricht ab, wenn Hintergrund-Tasks laufen. Der
Service-Guard bleibt die eigentliche Sicherung.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _ctrl():
    from ui.controllers.project_management import ProjectManagementController
    ctrl = ProjectManagementController.__new__(ProjectManagementController)
    ctrl.window = SimpleNamespace(status_bar=SimpleNamespace(showMessage=MagicMock()))
    return ctrl


# --- _tasks_running_block ------------------------------------------------

def test_b465_block_true_when_tasks_running():
    ctrl = _ctrl()
    with patch("services.project_manager.ProjectManager._has_running_tasks", return_value=True), \
         patch("ui.controllers.project_management.QMessageBox") as mb:
        blocked = ctrl._tasks_running_block("Projekt oeffnen")
    assert blocked is True
    mb.warning.assert_called_once()
    ctrl.window.status_bar.showMessage.assert_called_once()


def test_b465_block_false_when_idle():
    ctrl = _ctrl()
    with patch("services.project_manager.ProjectManager._has_running_tasks", return_value=False), \
         patch("ui.controllers.project_management.QMessageBox") as mb:
        blocked = ctrl._tasks_running_block("Projekt oeffnen")
    assert blocked is False
    mb.warning.assert_not_called()


def test_b465_block_false_on_lookup_error():
    """Pre-Block darf den echten Guard nie ersetzen — bei Fehler nicht blocken."""
    ctrl = _ctrl()
    with patch("services.project_manager.ProjectManager._has_running_tasks",
               side_effect=RuntimeError("boom")), \
         patch("ui.controllers.project_management.QMessageBox"):
        assert ctrl._tasks_running_block("Projekt oeffnen") is False


# --- _new_project / _open_project early-return ---------------------------

def test_b465_new_project_returns_before_dialog_when_blocked():
    ctrl = _ctrl()
    ctrl._tasks_running_block = MagicMock(return_value=True)
    with patch("ui.dialogs.project_dialog.NewProjectDialog") as dlg:
        ctrl._new_project()
    ctrl._tasks_running_block.assert_called_once_with("Neues Projekt")
    dlg.assert_not_called()


def test_b465_open_project_returns_before_dialog_when_blocked():
    ctrl = _ctrl()
    ctrl._tasks_running_block = MagicMock(return_value=True)
    with patch("ui.dialogs.project_dialog.OpenProjectDialog") as dlg:
        ctrl._open_project()
    ctrl._tasks_running_block.assert_called_once_with("Projekt oeffnen")
    dlg.assert_not_called()


def test_b465_new_project_proceeds_to_dialog_when_idle():
    """Bei idle wird der Dialog geoeffnet (hier abgebrochen via Rejected)."""
    from PySide6.QtWidgets import QDialog
    ctrl = _ctrl()
    ctrl._tasks_running_block = MagicMock(return_value=False)
    with patch("ui.dialogs.project_dialog.NewProjectDialog") as dlg:
        dlg.return_value.exec.return_value = QDialog.DialogCode.Rejected
        ctrl._new_project()
    dlg.assert_called_once()
