import pytest
import sys
from PySide6.QtWidgets import QApplication

# IMPORT ALL ACTIONS TO REGISTER THEM
import services.register_actions  # noqa: F401
from services.action_registry import action_registry
from pathlib import Path
import os


@pytest.fixture(scope="session", autouse=True)
def q_app():
    """Erstellt eine QApplication-Instanz für die Test-Sitzung, falls keine existiert."""
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    return app


def test_new_actions_registration():
    actions = action_registry.list_actions()
    assert "create_project" in actions
    assert "open_project" in actions
    assert "delete_media" in actions
    assert "clear_timeline" in actions
    assert "save_project" in actions


def test_save_project_action(monkeypatch):
    """save_project muss den ECHTEN Speicherpfad aufrufen.

    Statusaufnahme 2026-07-26: die Action gab hart ``status: ok`` /
    "erfolgreich gespeichert" zurueck, ohne irgendetwas zu tun — der ChatDock
    markierte das Projekt danach als sauber. Dieser Test prueft jetzt, dass
    ``ProjectManagementController._save_project`` wirklich gerufen wird.
    """
    # Wir erstellen ein minimales Dummy-Window, um activeWindow/PBWindow zu simulieren
    from PySide6.QtWidgets import QMainWindow
    called = {"n": 0}

    class PBWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.project_management = self
            self._dirty = True

        def _save_project(self):
            called["n"] += 1
            self._mark_clean()

        def _mark_clean(self):
            self._dirty = False

    app = QApplication.instance()
    window = PBWindow()
    window.show()

    # Die Action verlangt ein geoeffnetes Projekt (sonst gibt es nichts zu
    # speichern) — der ProjectManager wird dafuer gestellt.
    import services.actions.edit.project_actions as pa
    monkeypatch.setattr(
        pa, "_get_project_manager",
        lambda: type("_PM", (), {"current_project_path": "/tmp/testprojekt"})(),
    )

    res = action_registry.execute("save_project", {})
    assert res["status"] == "ok"
    assert res["action"] == "save_project"
    assert called["n"] == 1, "der echte Save-Pfad wurde nicht aufgerufen"
    assert window._dirty is False

    window.close()


def test_save_project_action_reports_error_without_project(monkeypatch):
    """Ohne geoeffnetes Projekt darf die Action keinen Erfolg melden."""
    from PySide6.QtWidgets import QMainWindow

    class PBWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.project_management = self

        def _save_project(self):
            raise AssertionError("darf ohne Projekt nicht gerufen werden")

    QApplication.instance()
    window = PBWindow()
    window.show()

    import services.actions.edit.project_actions as pa
    monkeypatch.setattr(
        pa, "_get_project_manager",
        lambda: type("_PM", (), {"current_project_path": None})(),
    )

    res = action_registry.execute("save_project", {})
    assert "error" in res
    assert res.get("status") != "ok"

    window.close()
