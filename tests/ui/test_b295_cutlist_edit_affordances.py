"""B-295: Die Cutliste braucht sichtbare Edit-Affordances.

Verifiziert das Rechtsklick-Kontextmenue (Sperren/Entsperren, Cut entfernen) im
CutListPanel, die Delegation an die bestehenden Timeline-Undo/DB-Commands und die
Verdrahtung im Schnitt-Tab.
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


def _panel_with_one_cut(entry_id=42, locked=False):
    import ui.widgets.cut_list_panel as mod
    _qapp()
    panel = mod.CutListPanel()
    panel._project_id = 1
    panel._render_cuts([{
        "index": 0, "entry_id": entry_id, "time": 1.0, "duration": 2.0,
        "locked": locked, "clip_id": 7, "title": "Clip 7",
    }])
    return mod, panel


def test_b295_row_stores_entry_id_and_locked():
    _mod, panel = _panel_with_one_cut(entry_id=99, locked=True)
    item = panel.table.item(0, 0)
    assert item.data(panel._ROLE_ENTRY_ID) == 99
    assert item.data(panel._ROLE_LOCKED) is True


def test_b295_context_menu_emits_lock_toggle():
    mod, panel = _panel_with_one_cut(entry_id=42, locked=False)
    captured = []
    panel.cut_lock_toggle_requested.connect(lambda eid, lk: captured.append((eid, lk)))

    # _exec_menu -> erste Action (Sperren/Entsperren)
    with patch.object(panel.table, "itemAt", return_value=panel.table.item(0, 0)), \
         patch.object(panel, "_exec_menu", lambda menu, gp: menu.actions()[0]):
        panel._on_context_menu(QPoint(1, 1))

    assert captured == [(42, True)], f"erwartet Lock-Toggle auf entry 42 -> True, war {captured}"


def test_b295_context_menu_emits_remove():
    mod, panel = _panel_with_one_cut(entry_id=42)
    captured = []
    panel.cut_remove_requested.connect(lambda eid: captured.append(eid))

    with patch.object(panel.table, "itemAt", return_value=panel.table.item(0, 0)), \
         patch.object(panel, "_exec_menu", lambda menu, gp: menu.actions()[1]):  # "Cut entfernen"
        panel._on_context_menu(QPoint(1, 1))

    assert captured == [42]


def test_b295_context_menu_noop_without_entry_id():
    mod, panel = _panel_with_one_cut(entry_id=42)
    panel.table.item(0, 0).setData(panel._ROLE_ENTRY_ID, None)  # kein entry_id
    fired = []
    panel.cut_remove_requested.connect(lambda eid: fired.append(eid))
    with patch.object(panel.table, "itemAt", return_value=panel.table.item(0, 0)), \
         patch.object(panel, "_exec_menu", lambda menu, gp: menu.actions()[1]):
        panel._on_context_menu(QPoint(1, 1))
    assert fired == []


# --- Timeline-Delegation -------------------------------------------------

def test_b295_timeline_lock_toggle_delegates_to_command():
    import ui.timeline as tl
    _qapp()
    view = tl.InteractiveTimeline()
    view.undo_stack = MagicMock()
    with patch.object(view, "_sync_clip_lock_visual"):
        view.toggle_clip_lock_by_id(5, True)
    assert view.undo_stack.push.call_count == 1
    pushed = view.undo_stack.push.call_args[0][0]
    from ui.undo_commands import ToggleClipLockCommand
    assert isinstance(pushed, ToggleClipLockCommand)


def test_b295_timeline_remove_delegates_to_command():
    import ui.timeline as tl
    _qapp()
    view = tl.InteractiveTimeline()
    view.undo_stack = MagicMock()
    view.remove_clip_by_id(5)
    assert view.undo_stack.push.call_count == 1
    pushed = view.undo_stack.push.call_args[0][0]
    from ui.undo_commands import RemoveClipCommand
    assert isinstance(pushed, RemoveClipCommand)


# --- Wiring + Service ----------------------------------------------------

def test_b295_tab_wires_context_menu_signals():
    from ui.workspaces.schnitt.tab_schnitt import SchnittTabSchnitt
    src = inspect.getsource(SchnittTabSchnitt)
    assert "cut_lock_toggle_requested.connect" in src
    assert "cut_remove_requested.connect" in src
    assert "toggle_clip_lock_by_id" in src
    assert "remove_clip_by_id" in src


def test_b295_get_cut_list_returns_entry_id():
    import inspect as _i
    import services.timeline_service as ts
    src = _i.getsource(ts.get_cut_list)
    assert '"entry_id"' in src
    assert "TimelineEntry.id" in src
