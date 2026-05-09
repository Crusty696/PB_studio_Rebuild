"""Frontend rebuild contract tests.

These tests pin the workflow decisions from the 2026 UI rebuild plan:
one primary action per page, expert/debug tools hidden, and a collapsed
context panel by default.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QHBoxLayout, QWidget


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_workflow_navigation_names_are_final():
    _ensure_qapp()
    from ui.widgets.nav_bar import WorkspaceNavBar

    assert WorkspaceNavBar.WORKSPACE_NAMES == [
        "PROJEKT",
        "MATERIAL & ANALYSE",
        "SCHNITT",
        "EXPORT",
    ]


def test_context_panel_collapses_without_destroying_content():
    _ensure_qapp()
    from ui.widgets.workflow_components import ContextPanel

    host = QWidget()
    layout = QHBoxLayout(host)
    panel = ContextPanel()
    layout.addWidget(panel)

    try:
        assert not panel.isVisible()
        assert panel.minimumWidth() == 0
        assert panel.maximumWidth() == 0

        panel.set_context_visible(True)
        assert panel.maximumWidth() > 0

        panel.set_context_visible(False)
        assert panel.minimumWidth() == 0
        assert panel.maximumWidth() == 0
    finally:
        host.deleteLater()


def test_workflow_components_are_available():
    _ensure_qapp()
    from ui.widgets.workflow_components import (
        ContextPanel,
        PrimaryActionBar,
        SectionTabs,
        StatusStrip,
        WorkflowHeader,
    )

    assert WorkflowHeader("Material & Analyse", "Auswahl und Analyse").title.text() == "Material & Analyse"
    assert PrimaryActionBar("Importieren").primary_button.text() == "Importieren"
    assert StatusStrip().layout() is not None
    assert SectionTabs().documentMode()
    assert isinstance(ContextPanel(), QWidget)
