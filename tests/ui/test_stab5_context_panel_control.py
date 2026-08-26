from __future__ import annotations

import inspect
import os
from types import MethodType, SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from main import PBWindow
from ui.controllers.workspace_setup import WorkspaceSetupController
from ui.widgets.workflow_components import ContextPanel


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _noop_namespace(*names: str) -> SimpleNamespace:
    return SimpleNamespace(**{name: (lambda: None) for name in names})


def test_context_button_click_toggles_real_panel_and_dock() -> None:
    app = _qapp()
    host = QMainWindow()
    central = QWidget(host)
    layout = QVBoxLayout(central)
    host.setCentralWidget(central)
    host.project_management = _noop_namespace(
        "_show_settings",
        "_new_project",
        "_open_project",
        "_save_project",
        "_save_project_as",
        "_show_shortcut_help",
        "_show_about",
    )
    host.import_media = _noop_namespace(
        "_import_video",
        "_import_audio",
        "_import_folder",
    )
    host.audio_analysis = _noop_namespace("_analyze_audio_v2")
    host._open_studio_brain = lambda: None

    host.right_panel = ContextPanel(host)
    host.right_dock = QDockWidget("Kontext", host)
    host.right_dock.setWidget(host.right_panel)
    host.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, host.right_dock)
    host._set_context_panel_visible = MethodType(
        PBWindow._set_context_panel_visible, host
    )
    host._on_context_dock_visibility_changed = MethodType(
        PBWindow._on_context_dock_visibility_changed, host
    )

    controller = WorkspaceSetupController(host)
    controller._build_top_bar(layout, "test")
    init_source = "".join(inspect.getsource(PBWindow.__init__).split())
    assert (
        "self._btn_context_panel.clicked.connect(self._set_context_panel_visible)"
        in init_source
    )
    assert (
        "self.right_dock.visibilityChanged.connect("
        "self._on_context_dock_visibility_changed)"
        in init_source
    )
    host._btn_context_panel.clicked.connect(host._set_context_panel_visible)
    host.right_dock.visibilityChanged.connect(
        host._on_context_dock_visibility_changed
    )

    try:
        host.show()
        app.processEvents()
        host._set_context_panel_visible(False)
        app.processEvents()

        assert host._btn_context_panel.isCheckable() is True
        assert host._btn_context_panel.text() == "Kontext"
        assert host._btn_context_panel.isChecked() is False
        assert host.right_panel.isHidden() is True
        assert host.right_panel.maximumWidth() == 0
        assert host.right_dock.isHidden() is True

        QTest.mouseClick(host._btn_context_panel, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert host._btn_context_panel.isChecked() is True
        assert host.right_panel.isVisible() is True
        assert host.right_panel.minimumWidth() == ContextPanel.MIN_WIDTH
        assert host.right_panel.maximumWidth() > ContextPanel.MIN_WIDTH
        assert host.right_dock.isVisible() is True

        QTest.mouseClick(host._btn_context_panel, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert host._btn_context_panel.isChecked() is False
        assert host.right_panel.isHidden() is True
        assert host.right_panel.maximumWidth() == 0
        assert host.right_dock.isHidden() is True
    finally:
        host.close()
        host.deleteLater()
        app.processEvents()
