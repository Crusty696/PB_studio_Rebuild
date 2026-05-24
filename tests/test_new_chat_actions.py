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


def test_save_project_action():
    # Wir erstellen ein minimales Dummy-Window, um activeWindow/PBWindow zu simulieren
    from PySide6.QtWidgets import QMainWindow
    class PBWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.project_management = self
            self._dirty = True
        def _mark_clean(self):
            self._dirty = False

    app = QApplication.instance()
    window = PBWindow()
    window.show()
    
    res = action_registry.execute("save_project", {})
    assert res["status"] == "ok"
    assert res["action"] == "save_project"
    assert "erfolgreich" in res["message"]
    
    window.close()
