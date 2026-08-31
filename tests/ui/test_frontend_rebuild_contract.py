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
    """Pinned the four names of the 2026 rebuild plan.

    Updated on 2026-08-31: CONVERT became a workflow step of its own (B-932,
    user decision "fifth rail button CONVERT"). Before that, the convert
    workspace was built but never mounted, so its progress bar and error
    messages went to widgets nobody could see. The count is part of the
    contract too - a fifth entry must not slip in unnoticed.
    """
    _ensure_qapp()
    from ui.widgets.nav_bar import WorkspaceNavBar

    assert WorkspaceNavBar.WORKSPACE_NAMES == [
        "PROJEKT",
        "MATERIAL & ANALYSE",
        "CONVERT",
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
        SectionTabs,
        StatusStrip,
        WorkflowHeader,
    )

    assert WorkflowHeader("Material & Analyse", "Auswahl und Analyse").title.text() == "Material & Analyse"
    assert StatusStrip().layout() is not None
    assert SectionTabs().documentMode()
    assert isinstance(ContextPanel(), QWidget)
