import pytest
from PySide6.QtWidgets import QApplication
from ui.windows.studio_brain_window import StudioBrainWindow
from ui.dialogs.story_map_dialog import StoryMapDialog
import sys

# Ensure a QApplication exists for the tests
@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app

def test_studio_brain_window_instantiation(qapp):
    """Test if StudioBrainWindow can be instantiated without crashing."""
    window = StudioBrainWindow()
    assert window is not None
    assert window.windowTitle() == "Studio Brain — Director's Cockpit"
    window.close()

def test_story_map_dialog_instantiation(qapp):
    """Test if StoryMapDialog can be instantiated without crashing."""
    # We use a dummy run_id. It might fail data loading but should instantiate.
    dialog = StoryMapDialog(run_id=999)
    assert dialog is not None
    dialog.close()

def test_studio_brain_tabs(qapp):
    """Test if all tabs are present in StudioBrainWindow."""
    window = StudioBrainWindow()
    assert window.tabs.count() == 4
    assert window.tabs.tabText(0) == "Structure"
    assert window.tabs.tabText(1) == "Memory"
    assert window.tabs.tabText(2) == "Audit"
    assert window.tabs.tabText(3) == "Steer"
    window.close()
