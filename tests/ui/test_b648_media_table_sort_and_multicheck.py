"""B-648 + Checkbox-fuer-Markierte (User 2026-07-17).

- MediaTableModel.sort(): typbewusste Spalten-Sortierung (ID/FPS/% numerisch,
  Aufloesung nach Pixelflaeche, Titel case-insensitiv), paginated_fetch-Reset.
- set_checked_for_ids(): Haken fuer ID-Teilmenge (Grundlage 'nur markierte
  anhaken'), inkl. PagedProxyModel-Pass-Through.
- View: Video-Pool hat setSortingEnabled (Source-Pin).
"""
from __future__ import annotations

import inspect

from PySide6.QtCore import Qt

from ui.models.media_table_model import MediaTableModel, PagedProxyModel


def _items():
    return [
        {"id": 3, "title": "beta", "resolution": "1920x1080", "fps": 25.0,
         "codec": "h264", "analysis_percent": 40, "file_path": "c.mp4"},
        {"id": 1, "title": "Alpha", "resolution": "640x480", "fps": 60.0,
         "codec": "hevc", "analysis_percent": 100, "file_path": "a.mp4"},
        {"id": 2, "title": "gamma", "resolution": "3840x2160", "fps": 30.0,
         "codec": None, "analysis_percent": 0, "file_path": "b.mp4"},
    ]


def test_sort_by_id_numeric():
    m = MediaTableModel(media_type="Video")
    m.set_items(_items())
    m.sort(1, Qt.SortOrder.AscendingOrder)  # Spalte 1 = ID
    assert [i["id"] for i in m._items] == [1, 2, 3]
    m.sort(1, Qt.SortOrder.DescendingOrder)
    assert [i["id"] for i in m._items] == [3, 2, 1]


def test_sort_by_resolution_pixel_area_not_string():
    m = MediaTableModel(media_type="Video")
    m.set_items(_items())
    m.sort(3, Qt.SortOrder.AscendingOrder)  # Spalte 3 = Aufloesung
    # Pixelflaeche: 640x480 < 1920x1080 < 3840x2160 (String-Sortierung
    # wuerde "1920..." vor "3840..." vor "640..." liefern)
    assert [i["resolution"] for i in m._items] == [
        "640x480", "1920x1080", "3840x2160"]


def test_sort_by_title_case_insensitive_none_last():
    m = MediaTableModel(media_type="Video")
    m.set_items(_items())
    m.sort(2, Qt.SortOrder.AscendingOrder)  # Spalte 2 = Titel
    assert [i["title"] for i in m._items] == ["Alpha", "beta", "gamma"]
    m.sort(5, Qt.SortOrder.AscendingOrder)  # Spalte 5 = Codec (None dabei)
    assert m._items[-1]["codec"] is None  # leere Werte ans Ende


def test_sort_resets_paginated_fetch_window():
    m = MediaTableModel(media_type="Video", paginated_fetch=True)
    m._INITIAL_FETCH_ROWS = 2
    m.set_items(_items())
    assert m.rowCount() == 2
    m.sort(1, Qt.SortOrder.DescendingOrder)
    assert m.rowCount() == 2  # nach Sortierung wieder nur erster Ausschnitt
    assert m.canFetchMore()


def test_set_checked_for_ids_and_proxy_passthrough():
    m = MediaTableModel(media_type="Video")
    m.set_items(_items())
    m.set_checked_for_ids([1, 3, 999], True)  # 999 existiert nicht
    assert sorted(m.get_checked_ids()) == [1, 3]
    m.set_checked_for_ids([3], False)
    assert m.get_checked_ids() == [1]

    proxy = PagedProxyModel(page_size=10)
    proxy.setSourceModel(m)
    proxy.set_checked_for_ids([2], True)
    assert sorted(proxy.get_checked_ids()) == [1, 2]


def test_video_pool_view_has_sorting_enabled_pin():
    import ui.workspaces.media_workspace as mw
    src = inspect.getsource(mw.MediaWorkspace) if hasattr(mw, "MediaWorkspace") \
        else open(mw.__file__, encoding="utf-8").read()
    assert "video_pool_table.setSortingEnabled(True)" in src, (
        "B-648: Video-Pool muss Header-Klick-Sortierung aktiviert haben.")


def test_view_multicheck_applies_to_selection_pin():
    import ui.workspaces.media_workspace as mw
    src = inspect.getsource(mw.DraggablePoolView)
    assert "set_checked_for_ids" in src, (
        "Checkbox-fuer-Markierte: Klick auf Checkbox einer markierten Zeile "
        "muss den Zustand auf die ganze Auswahl anwenden.")
    assert "contextMenuEvent" in src
