"""P0 #3: QWebChannel-Bridge im Graph-Cockpit-Tab."""
from __future__ import annotations

import pytest

PySide6 = pytest.importorskip("PySide6")
pytestqt = pytest.importorskip("pytestqt")

from services.graph.cockpit_view_model import CockpitViewModel
from services.graph.graph_service import GraphService
from ui.widgets.graph_cockpit_tab import GraphCockpitTab, _CockpitBridge


def _vm():
    g = GraphService()
    g.add_node("a", "audio", "Audio A")
    g.add_node("b", "video", "Video B")
    g.add_edge("a", "b", "matched", 0.85)
    return CockpitViewModel(graph=g)


def test_bridge_emits_signal_on_click(qtbot):
    bridge = _CockpitBridge()
    received: list[str] = []
    bridge.nodeClickedFromJs.connect(lambda n: received.append(n))
    bridge.onNodeClicked("a")
    assert received == ["a"]


def test_tab_has_bridge_when_qwebengine_available(qtbot):
    tab = GraphCockpitTab(view_model=_vm())
    qtbot.addWidget(tab)
    if tab.web_view is None:
        pytest.skip("QWebEngineView nicht installiert")
    if tab._channel_cls is None:
        pytest.skip("QtWebChannel nicht installiert")
    assert tab._bridge is not None
    assert tab._channel is not None


def test_bridge_click_routes_to_select_node(qtbot):
    """JS clickNode → bridge.onNodeClicked → tab.select_node."""
    tab = GraphCockpitTab(view_model=_vm())
    qtbot.addWidget(tab)
    if tab._bridge is None:
        pytest.skip("Bridge nicht initialisiert")
    received: list[str] = []
    tab.nodeSelected.connect(lambda n: received.append(n))
    # Simuliere JS-Klick durch direkten Bridge-Slot-Aufruf
    tab._bridge.onNodeClicked("a")
    assert received == ["a"]
    detail = tab.detail_text.toPlainText()
    assert "Audio A" in detail


def test_sigma_html_contains_qwebchannel_script(qtbot):
    """Generiertes HTML referenziert qwebchannel.js."""
    from services.graph.sigma_renderer import render_sigma_html
    html = render_sigma_html(_vm().graph)
    assert "qwebchannel.js" in html
    assert "cockpitBridge" in html
    assert "onNodeClicked" in html
