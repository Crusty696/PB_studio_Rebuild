"""Bug E regression: einzelne Checkboxen im Media Pool muessen klickbar sein.

DraggablePoolView hat setDragEnabled(True) + SelectRows. Vor dem Fix
verschluckte Qt's Drag-Initiation den Click auf die Checkbox-Spalte —
der "Alle"-Button funktionierte (toggle_all() am Model direkt), aber
einzelne Checkboxen liessen sich nicht aktivieren.

Fix: DraggablePoolView.mousePressEvent fängt Clicks auf Spalte 0 ab und
toggelt den CheckState explizit, ohne Drag zu starten.

Diese Tests verifizieren das Verhalten ohne echte QMouseEvents auf Pixel-
Positionen — wir simulieren den Press direkt am Index, was identisch ist
zum Pfad den die View nimmt nachdem sie indexAt() aufgerufen hat.
"""

from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from ui.models.media_table_model import MediaTableModel, PagedProxyModel
from ui.workspaces.media_workspace import DraggablePoolView


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_view_with_data(items: list[dict[str, Any]]) -> DraggablePoolView:
    """Konstruiert eine DraggablePoolView mit Source+Proxy+Daten — passt
    zur realen Setup-Struktur in MediaWorkspace."""
    _ensure_qapp()
    src = MediaTableModel(media_type="Video")
    proxy = PagedProxyModel(page_size=16)
    proxy.setSourceModel(src)
    src.set_items(items)
    view = DraggablePoolView(track_type="video")
    view.setModel(proxy)
    return view


def _click_index(view: DraggablePoolView, index) -> None:
    """Simuliere einen Linksklick auf die übergebene Modellzelle.

    Erstellt einen echten QMouseEvent — die View's mousePressEvent
    Override soll den Click auf die Checkbox-Spalte abfangen und
    toggeln. Wir umgehen indexAt() indem wir das visualRect der Cell
    nehmen und im Center klicken.
    """
    rect = view.visualRect(index)
    pos = QPointF(rect.center())
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        pos,
        pos,  # globalPos — same for offscreen
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    view.mousePressEvent(event)


def test_single_checkbox_click_toggles_check_state() -> None:
    """Click auf die Checkbox-Spalte toggelt den CheckState (Bug E)."""
    items = [
        {"id": 1, "title": "Clip A", "resolution": "1920x1080", "fps": 30,
         "codec": "h264", "analysis_percent": 0, "file_path": "/a.mp4"},
        {"id": 2, "title": "Clip B", "resolution": "1920x1080", "fps": 30,
         "codec": "h264", "analysis_percent": 0, "file_path": "/b.mp4"},
        {"id": 3, "title": "Clip C", "resolution": "1920x1080", "fps": 30,
         "codec": "h264", "analysis_percent": 0, "file_path": "/c.mp4"},
    ]
    view = _make_view_with_data(items)
    view.show()  # nötig damit visualRect geometrisch sinnvolle Werte liefert
    view.resize(800, 200)

    src = view.model().sourceModel()  # MediaTableModel
    assert src.get_checked_ids() == [], "Start: nichts ausgewählt"

    # Click auf Zeile 1, Spalte 0 (Checkbox)
    proxy_index = view.model().index(1, 0)
    _click_index(view, proxy_index)

    assert 2 in src.get_checked_ids(), \
        "Nach Click muss Item 2 in checked_ids stehen"

    # Zweiter Click toggelt zurück
    _click_index(view, proxy_index)
    assert 2 not in src.get_checked_ids(), \
        "Nach zweitem Click muss Item 2 wieder unchecked sein"


def test_click_on_non_checkbox_column_does_not_toggle() -> None:
    """Clicks auf andere Spalten (ID, Titel, Pfad…) duerfen nicht toggeln."""
    items = [
        {"id": 1, "title": "Clip A", "resolution": "1920x1080", "fps": 30,
         "codec": "h264", "analysis_percent": 0, "file_path": "/a.mp4"},
    ]
    view = _make_view_with_data(items)
    view.show()
    view.resize(800, 200)

    src = view.model().sourceModel()

    # Click auf Spalte 2 (Titel) — sollte NICHT toggeln
    proxy_index = view.model().index(0, 2)
    _click_index(view, proxy_index)

    assert src.get_checked_ids() == [], \
        "Click auf Titel-Spalte darf den CheckState nicht ändern"


def test_multiple_checkbox_clicks_independent() -> None:
    """Mehrere Zeilen unabhängig toggelbar (kein Cross-Talk)."""
    items = [
        {"id": 10, "title": "A", "resolution": "1920x1080", "fps": 30,
         "codec": "h264", "analysis_percent": 0, "file_path": "/a.mp4"},
        {"id": 20, "title": "B", "resolution": "1920x1080", "fps": 30,
         "codec": "h264", "analysis_percent": 0, "file_path": "/b.mp4"},
        {"id": 30, "title": "C", "resolution": "1920x1080", "fps": 30,
         "codec": "h264", "analysis_percent": 0, "file_path": "/c.mp4"},
    ]
    view = _make_view_with_data(items)
    view.show()
    view.resize(800, 200)
    src = view.model().sourceModel()

    # Drei einzelne Klicks
    _click_index(view, view.model().index(0, 0))
    _click_index(view, view.model().index(2, 0))

    assert sorted(src.get_checked_ids()) == [10, 30], \
        f"Erwartet [10, 30], bekommen {sorted(src.get_checked_ids())}"

    # Item 10 wieder abwählen, 20 dazu
    _click_index(view, view.model().index(0, 0))
    _click_index(view, view.model().index(1, 0))

    assert sorted(src.get_checked_ids()) == [20, 30], \
        f"Erwartet [20, 30], bekommen {sorted(src.get_checked_ids())}"


def test_checkbox_state_persists_after_data_refresh() -> None:
    """Set_items mit gleichen IDs darf bestehende Selektion nicht löschen.

    Das ist nicht der Bug-E-Fix, aber eine wichtige Invariante die wir
    nebenbei verifizieren — sonst gehen Selektionen bei jedem
    Pipeline-Refresh verloren.
    """
    items = [
        {"id": 1, "title": "A", "resolution": "1920x1080", "fps": 30,
         "codec": "h264", "analysis_percent": 0, "file_path": "/a.mp4"},
        {"id": 2, "title": "B", "resolution": "1920x1080", "fps": 30,
         "codec": "h264", "analysis_percent": 0, "file_path": "/b.mp4"},
    ]
    view = _make_view_with_data(items)
    view.show()
    view.resize(800, 200)
    src = view.model().sourceModel()

    # Item 1 anklicken
    _click_index(view, view.model().index(0, 0))
    assert 1 in src.get_checked_ids()

    # Refresh mit GLEICHEN Items (z.B. nach Pipeline-Update) — sollte
    # die Selektion erhalten.
    src.set_items(items)
    assert 1 in src.get_checked_ids(), \
        "set_items mit gleichen IDs darf bestehende Selektion nicht löschen"

    # Refresh mit ANDEREN Items — Item 1 nicht mehr drin → wird entfernt
    src.set_items([{"id": 99, "title": "Z", "resolution": "1920x1080", "fps": 30,
                    "codec": "h264", "analysis_percent": 0, "file_path": "/z.mp4"}])
    assert 1 not in src.get_checked_ids(), \
        "Item 1 nicht mehr in den neuen Daten → muss aus checked_ids verschwinden"
