"""Smoke-Tests fuer ui/controllers/ — Tier-2 Coverage-Drift-Stop.

Vorher: 13 Controller (3439 LOC) hatten genau **1 dezidierten Test**
(``test_stems_controller_lazy_taskmanager.py``). Drei autonome Loop-
Cycles haben das als groesste Coverage-Luecke nach ``ui/workspaces/``
identifiziert.

Strategie: minimaler Smoke-Test pro Controller — ``PBComponent``-Subclass
laesst sich mit einem Mock-PBWindow konstruieren ohne zu crashen, und
exposed-State (window-Ref + Logger) ist da. Komplexere Pfade wie
Worker-Trigger / DB-Roundtrips bleiben fuer dezidierte Integration-Tests.

Pattern entlehnt aus ``test_stems_controller_lazy_taskmanager.py`` —
Mock + lokaler Import + Konstruktor-Check.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtWidgets import QApplication


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(scope="module", autouse=True)
def qapp() -> QApplication:
    return _ensure_qapp()


@pytest.fixture
def mock_window() -> MagicMock:
    """Mock-PBWindow mit den haeufigen Attributen die Controller-
    Konstruktoren lesen. Defensive: wir geben ``logger``, ``status_bar``,
    ``console_text`` als MagicMocks — nicht jeder Controller braucht
    sie, aber wenn doch, dann crasht der ctor nicht.
    """
    win = MagicMock()
    win.logger = MagicMock()
    win.status_bar = MagicMock()
    win.console_text = MagicMock()
    win._project_manager = None
    win.right_panel = MagicMock()
    win.chat_dock = MagicMock()
    return win


# --------------------------------------------------------------------------
# 13 Controller × 1 Smoke-Test
# --------------------------------------------------------------------------

def test_audio_analysis_controller_constructs(mock_window) -> None:
    from ui.controllers.audio_analysis import AudioAnalysisController

    ctl = AudioAnalysisController(mock_window)
    assert ctl.window is mock_window


def test_convert_controller_constructs(mock_window) -> None:
    from ui.controllers.convert import ConvertController

    ctl = ConvertController(mock_window)
    assert ctl.window is mock_window


def test_edit_workspace_controller_constructs(mock_window) -> None:
    from ui.controllers.edit_workspace import EditWorkspaceController

    ctl = EditWorkspaceController(mock_window)
    assert ctl.window is mock_window


def test_export_controller_constructs(mock_window) -> None:
    from ui.controllers.export import ExportController

    ctl = ExportController(mock_window)
    assert ctl.window is mock_window


def test_import_media_controller_constructs(mock_window) -> None:
    from ui.controllers.import_media import ImportMediaController

    ctl = ImportMediaController(mock_window)
    assert ctl.window is mock_window


def test_media_table_controller_constructs(mock_window) -> None:
    from ui.controllers.media_table import MediaTableController

    ctl = MediaTableController(mock_window)
    assert ctl.window is mock_window


def test_panel_setup_controller_constructs(mock_window) -> None:
    from ui.controllers.panel_setup import PanelSetupController

    ctl = PanelSetupController(mock_window)
    assert ctl.window is mock_window


def test_project_management_controller_constructs(mock_window) -> None:
    from ui.controllers.project_management import ProjectManagementController

    ctl = ProjectManagementController(mock_window)
    assert ctl.window is mock_window
    # B-050: Project-Error-Handler-Builder ist intern — Aufruf darf
    # nicht crashen mit einem Mock-Window.
    handler = ctl._make_project_error_handler("Test")
    assert callable(handler)


def test_search_controller_constructs(mock_window) -> None:
    from ui.controllers.search import SearchController

    ctl = SearchController(mock_window)
    assert ctl.window is mock_window


def test_stems_controller_constructs(mock_window) -> None:
    from ui.controllers.stems import StemsController

    ctl = StemsController(mock_window)
    assert ctl.window is mock_window


def test_video_analysis_controller_constructs(mock_window) -> None:
    from ui.controllers.video_analysis import VideoAnalysisController

    ctl = VideoAnalysisController(mock_window)
    assert ctl.window is mock_window


def test_worker_dispatcher_controller_constructs(mock_window) -> None:
    from ui.controllers.worker_dispatcher import WorkerDispatcherController

    ctl = WorkerDispatcherController(mock_window)
    assert ctl.window is mock_window


def test_workspace_setup_controller_constructs(mock_window) -> None:
    from ui.controllers.workspace_setup import WorkspaceSetupController

    ctl = WorkspaceSetupController(mock_window)
    assert ctl.window is mock_window


# --------------------------------------------------------------------------
# Index-Drift-Stop: ui.controllers re-exported alle 13
# --------------------------------------------------------------------------

def test_all_controllers_exported_from_package() -> None:
    import ui.controllers as ctrl_pkg

    expected = {
        "AudioAnalysisController",
        "ConvertController",
        "EditWorkspaceController",
        "ExportController",
        "ImportMediaController",
        "MediaTableController",
        "PanelSetupController",
        "ProjectManagementController",
        "SearchController",
        "StemsController",
        "VideoAnalysisController",
        "WorkerDispatcherController",
        "WorkspaceSetupController",
    }
    actual = set(getattr(ctrl_pkg, "__all__", []))
    missing = expected - actual
    assert not missing, f"ui.controllers fehlt im __all__: {missing}"
    # Plus tatsaechliche Importierbarkeit
    for name in expected:
        assert hasattr(ctrl_pkg, name), f"ui.controllers.{name} nicht importierbar"
