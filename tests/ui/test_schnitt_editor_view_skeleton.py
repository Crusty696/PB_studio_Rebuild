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
    # Pro-Editor-Umbau 2026-07-10: Inspector lebt im oberen Band des
    # Schnitt-Tabs (in einer QFrame-Box neben der Vorschau); editor_view
    # haelt den Alias fuer Controller/Wiring. Invariante: Attribut existiert
    # + haengt im editor_view-Widget-Baum.
    assert v.inspector_panel is v.tab_schnitt.inspector_panel
    p = v.inspector_panel.parent()
    seen = set()
    while p is not None and id(p) not in seen:
        seen.add(id(p))
        if p is v:
            break
        p = p.parent()
    assert p is v, "inspector_panel muss im editor_view-Widget-Baum haengen"
