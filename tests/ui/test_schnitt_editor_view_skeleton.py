"""Skeleton-Test fuer SchnittEditorView (Phase 04 / Task 4.2)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from ui.workspaces.schnitt.editor_view import SchnittEditorView


def _qapp():
    return QApplication.instance() or QApplication([])


def test_editor_has_four_subtabs():
    _qapp()
    v = SchnittEditorView()
    titles = [v.sub_tabs.tabText(i) for i in range(v.sub_tabs.count())]
    assert titles == ["Schnitt", "Pacing & Anker", "Audio", "RL & Notes"]


def test_editor_has_persistent_inspector():
    _qapp()
    v = SchnittEditorView()
    assert v.inspector_panel is not None
    assert v.inspector_panel.parent() is v
