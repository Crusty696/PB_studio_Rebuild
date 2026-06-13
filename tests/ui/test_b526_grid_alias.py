"""B-526: Die Kachelansicht (MediaPoolGrid) blieb dauerhaft LEER, weil
``window.video_grid`` / ``window.audio_grid`` nie als Alias gesetzt wurden.
MediaTableController._apply_refreshed_data ruft ``set_items`` nur, wenn
``hasattr(window, "video_grid")`` — ohne Alias war das False, das Grid bekam nie
Daten.
"""
from __future__ import annotations

import inspect
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace
from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


def test_b526_workspace_setup_aliases_grids_on_window():
    """Der Fix: workspace_setup verdrahtet video_grid/audio_grid als window-Alias."""
    from ui.controllers.workspace_setup import WorkspaceSetupController

    src = inspect.getsource(WorkspaceSetupController._create_workspaces)
    assert "self.window.video_grid = self.window._media_ws.video_grid" in src
    assert "self.window.audio_grid = self.window._media_ws.audio_grid" in src


def test_b526_media_workspace_exposes_grids():
    _qapp()
    from ui.workspaces.media_workspace import MediaWorkspace

    ws = MediaWorkspace()
    assert hasattr(ws, "video_grid")
    assert hasattr(ws, "audio_grid")


def test_b526_apply_refreshed_data_feeds_grid_when_aliased():
    """Mit gesetztem window.video_grid fuettert der Controller das Grid."""
    from ui.controllers.media_table import MediaTableController

    ctrl = MediaTableController.__new__(MediaTableController)
    video_grid = MagicMock()
    audio_grid = MagicMock()
    ctrl.window = SimpleNamespace(
        video_pool_model=MagicMock(),
        audio_pool_model=MagicMock(),
        video_grid=video_grid,
        audio_grid=audio_grid,
    )

    videos = [{"id": 1, "title": "v"}]
    audios = [{"id": 2, "title": "a"}]
    MediaTableController._apply_refreshed_data(ctrl, videos, audios, also_combos=False)

    video_grid.set_items.assert_called_once_with(videos)
    audio_grid.set_items.assert_called_once_with(audios)
