"""P1.5: Graph-Cockpit-Tab headless tests."""
from __future__ import annotations

import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from services.graph.cockpit_view_model import CockpitViewModel
from services.graph.graph_service import GraphService
from ui.widgets.graph_cockpit_tab import GraphCockpitTab


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _build_vm_with_graph():
    g = GraphService()
    g.add_node("a", "audio", "Audio A")
    g.add_node("b", "video", "Video B")
    g.add_node("c", "video", "Video C")
    g.add_edge("a", "b", "matched", 0.85)
    g.add_edge("a", "c", "matched", 0.5)
    return CockpitViewModel(graph=g)


def test_tab_renders_stats(qapp):
    vm = _build_vm_with_graph()
    tab = GraphCockpitTab(view_model=vm)
    text_ = tab.stats_label.text()
    assert "3" in text_  # 3 nodes
    assert "2" in text_  # 2 edges


def test_select_node_updates_detail(qapp):
    vm = _build_vm_with_graph()
    tab = GraphCockpitTab(view_model=vm)
    tab.select_node("a")
    detail = tab.detail_text.toPlainText()
    assert "Audio A" in detail
    assert "audio" in detail
    # Neighbors zeigen target-IDs (b, c) + edge-type
    assert "b" in detail or "c" in detail
    assert "matched" in detail


def test_select_unknown_node_shows_error_msg(qapp):
    vm = _build_vm_with_graph()
    tab = GraphCockpitTab(view_model=vm)
    tab.select_node("ghost")
    detail = tab.detail_text.toPlainText()
    assert "ghost" in detail


def test_node_selected_signal_fires(qapp):
    vm = _build_vm_with_graph()
    tab = GraphCockpitTab(view_model=vm)
    received: list[str] = []
    tab.nodeSelected.connect(lambda n: received.append(n))
    tab.select_node("a")
    assert received == ["a"]


def test_set_view_model_refreshes(qapp):
    tab = GraphCockpitTab(view_model=CockpitViewModel())
    initial_stats = tab.stats_label.text()
    new_vm = _build_vm_with_graph()
    tab.set_view_model(new_vm)
    new_stats = tab.stats_label.text()
    assert new_stats != initial_stats
