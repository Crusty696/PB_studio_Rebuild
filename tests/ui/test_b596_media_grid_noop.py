"""B-596: Media grid darf bei identischen Items keinen Card-Rebuild starten."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


def test_b596_identical_video_items_do_not_rebuild_cards(monkeypatch, tmp_path):
    from ui.widgets.media_grid import MediaPoolGrid

    _qapp()
    grid = MediaPoolGrid(media_type="video")
    calls: list[tuple[int, ...]] = []

    def fake_rebuild() -> None:
        calls.append(tuple(item["id"] for item in grid._all_items))

    monkeypatch.setattr(grid, "_rebuild_cards", fake_rebuild)
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"fake video")
    items = [
        {
            "id": 1,
            "title": "Clip",
            "file_path": str(path),
            "resolution": "1920x1080",
            "fps": 30.0,
        }
    ]

    try:
        grid.set_items(items)
        grid.set_items([dict(items[0])])

        assert calls == [(1,)]
    finally:
        grid.deleteLater()


def test_b596_changed_video_item_rebuilds_cards(monkeypatch, tmp_path):
    from ui.widgets.media_grid import MediaPoolGrid

    _qapp()
    grid = MediaPoolGrid(media_type="video")
    calls: list[tuple[str, ...]] = []

    def fake_rebuild() -> None:
        calls.append(tuple(item["title"] for item in grid._all_items))

    monkeypatch.setattr(grid, "_rebuild_cards", fake_rebuild)
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"fake video")

    try:
        grid.set_items(
            [
                {
                    "id": 1,
                    "title": "Clip",
                    "file_path": str(path),
                    "resolution": "1920x1080",
                    "fps": 30.0,
                }
            ]
        )
        grid.set_items(
            [
                {
                    "id": 1,
                    "title": "Clip done",
                    "file_path": str(path),
                    "resolution": "1920x1080",
                    "fps": 30.0,
                }
            ]
        )

        assert calls == [("Clip",), ("Clip done",)]
    finally:
        grid.deleteLater()
