from __future__ import annotations

import inspect
import os
from types import MethodType, SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QLabel,
    QMainWindow,
    QPushButton,
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


def test_tools_tasks_action_reaches_hidden_proxy_and_tasks_tab() -> None:
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
        "_import_video", "_import_audio", "_import_folder"
    )
    host.audio_analysis = _noop_namespace("_analyze_audio_v2")
    host._open_studio_brain = lambda: None
    host.right_panel = ContextPanel(host)
    host.right_panel.addTab(QLabel("Task-Inhalt"), "Tasks")
    host.right_panel.addTab(QLabel("Log-Inhalt"), "Log")
    host.right_panel.setCurrentIndex(1)
    host.right_dock = QDockWidget("Kontext", host)
    host.right_dock.setWidget(host.right_panel)
    host.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, host.right_dock)
    host._set_context_panel_visible = MethodType(
        PBWindow._set_context_panel_visible, host
    )
    controller = WorkspaceSetupController(host)
    controller._build_top_bar(layout, "test")

    init_source_raw = inspect.getsource(PBWindow.__init__)
    closure_start = init_source_raw.index("def _to_tab")
    closure_end = init_source_raw.index(
        "self._btn_toggle_tasks.clicked.connect", closure_start
    )
    closure_source = "".join(
        init_source_raw[closure_start:closure_end].split()
    )
    assert "self._set_context_panel_visible(True)" in closure_source
    assert "foriinrange(self.right_panel.count()):" in closure_source
    assert (
        "iflabel_substring.lower()inself.right_panel.tabText(i).lower():"
        in closure_source
    )
    assert "self.right_panel.setCurrentIndex(i)" in closure_source
    assert "return" in closure_source
    init_source = "".join(init_source_raw.split())
    assert (
        'self._btn_toggle_tasks.clicked.connect(lambda:_to_tab("tasks"))'
        in init_source
    )

    def _to_tasks_tab() -> None:
        host._set_context_panel_visible(True)
        for index in range(host.right_panel.count()):
            if "tasks" in host.right_panel.tabText(index).lower():
                host.right_panel.setCurrentIndex(index)
                return

    host._btn_toggle_tasks.clicked.connect(_to_tasks_tab)
    tools_buttons = [
        button
        for button in host.findChildren(QPushButton)
        if button.text() == "Tools"
    ]
    assert len(tools_buttons) == 1
    tasks_actions = [
        action
        for action in tools_buttons[0].menu().actions()
        if action.text() == "Tasks anzeigen"
    ]
    assert len(tasks_actions) == 1

    try:
        host.show()
        app.processEvents()
        host._set_context_panel_visible(False)
        app.processEvents()
        assert tools_buttons[0].isVisible() is True
        assert tasks_actions[0].isVisible() is True
        assert tasks_actions[0].isEnabled() is True
        assert host._btn_toggle_tasks.isHidden() is True
        assert host.right_panel.currentIndex() == 1

        tasks_actions[0].trigger()
        app.processEvents()

        assert host._btn_toggle_tasks.isHidden() is True
        assert host.right_panel.isVisible() is True
        assert host.right_dock.isVisible() is True
        assert host.right_panel.tabText(host.right_panel.currentIndex()) == "Tasks"
    finally:
        host.close()
        host.deleteLater()
        app.processEvents()
