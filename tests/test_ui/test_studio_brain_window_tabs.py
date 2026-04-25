"""P0 #2: Cycle 11 Tab-Registrierung — Decision-Explorer + Graph-Cockpit
sind im StudioBrainWindow präsent."""
from __future__ import annotations

import pytest

PySide6 = pytest.importorskip("PySide6")
pytestqt = pytest.importorskip("pytestqt")

from ui.studio_brain_window import _TAB_LABELS


def test_tab_labels_contain_cycle11_tabs():
    assert "Pacing-Explorer" in _TAB_LABELS
    assert "Graph-Cockpit" in _TAB_LABELS
    # Indices fixiert für Cross-Tab-Wiring
    assert _TAB_LABELS.index("Pacing-Explorer") == 4
    assert _TAB_LABELS.index("Graph-Cockpit") == 5


def test_imports_resolve():
    """Cycle-11-Imports im Window-Modul müssen alle laden."""
    from ui.widgets.pacing_decision_explorer import PacingDecisionExplorer
    from ui.widgets.graph_cockpit_tab import GraphCockpitTab
    from services.graph.cockpit_view_model import CockpitViewModel
    assert PacingDecisionExplorer is not None
    assert GraphCockpitTab is not None
    assert CockpitViewModel is not None
