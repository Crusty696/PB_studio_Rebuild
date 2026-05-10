"""B-295: CutListPanel renders cuts from get_cut_list."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from ui.widgets.cut_list_panel import CutListPanel


def test_b295_cut_list_panel_renders_empty(qapp):
    panel = CutListPanel()
    panel.set_project(None)
    assert panel.rendered_row_count() == 0


def test_b295_cut_list_panel_renders_cuts(qapp, monkeypatch):
    # M-5: get_cut_list ist Modul-top-Import in cut_list_panel — patchen
    # muss daher die gebundene Referenz im Konsumenten-Modul, nicht
    # services.timeline_service.
    import ui.widgets.cut_list_panel as clp

    def fake_get_cut_list(pid):
        return [
            {"index": 0, "time": 0.0, "duration": 2.5, "source": "beat",
             "strength": 0.9, "locked": False, "clip_id": 1, "title": "clip_a"},
            {"index": 1, "time": 2.5, "duration": 1.5, "source": "anchor",
             "strength": 0.7, "locked": True, "clip_id": 2, "title": "clip_b"},
        ]
    monkeypatch.setattr(clp, "get_cut_list", fake_get_cut_list)

    panel = CutListPanel()
    panel.set_project(42)
    assert panel.rendered_row_count() == 2


def test_b295_cut_list_panel_cut_selected_signal(qapp, monkeypatch):
    import ui.widgets.cut_list_panel as clp
    monkeypatch.setattr(clp, "get_cut_list", lambda pid: [
        {"index": 0, "time": 1.5, "duration": 1.0, "source": "beat",
         "strength": 0.9, "locked": False, "clip_id": 1, "title": "c1"},
    ])
    panel = CutListPanel()
    panel.set_project(1)
    captured = []
    panel.cut_selected.connect(lambda t: captured.append(t))
    # simulate cell click on row 0 col 1 (time)
    panel._on_cell_clicked(0, 1)
    assert captured == [1.5]


def test_b295_cut_list_panel_has_5_columns(qapp):
    """I-1: 5 Spalten (#, Zeit, Dauer, Lock, Clip). Source+Strength entfernt
    bis Schema-Migration cut_source/cut_strength persistent macht."""
    panel = CutListPanel()
    assert panel.table.columnCount() == 5
    headers = [panel.table.horizontalHeaderItem(i).text() for i in range(5)]
    assert headers == ["#", "Zeit", "Dauer", "Lock", "Clip"]


def test_b295_cut_list_panel_cut_selected_uses_userrole(qapp, monkeypatch):
    """I-2: cut_selected liest UserRole-Daten (Locale-safe Float),
    nicht Display-String (der nur auf 2 Nachkommastellen rundet)."""
    import ui.widgets.cut_list_panel as clp
    monkeypatch.setattr(clp, "get_cut_list", lambda pid: [
        {"index": 0, "time": 3.14159, "duration": 1.0, "source": "beat",
         "strength": 0.5, "locked": False, "clip_id": 1, "title": "c"},
    ])
    panel = CutListPanel()
    panel.set_project(1)
    captured = []
    panel.cut_selected.connect(lambda t: captured.append(t))
    panel._on_cell_clicked(0, 1)
    # Wert kommt aus UserRole = float(time) = 3.14159, nicht aus dem
    # gerundeten Display "3.14s".
    assert captured == [3.14159]
