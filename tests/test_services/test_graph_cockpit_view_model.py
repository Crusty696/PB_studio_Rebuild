"""D-023 P4 Logik-Layer."""
from services.graph.graph_service import GraphService
from services.graph.cockpit_view_model import CockpitViewModel


def test_render_empty():
    vm = CockpitViewModel()
    html = vm.render_html()
    assert "<html" in html.lower()
    assert vm.stats() == {"n_nodes": 0, "n_edges": 0}


def test_select_node_returns_neighbors():
    g = GraphService()
    g.add_node("a", "audio", "A")
    g.add_node("b", "video", "B")
    g.add_edge("a", "b", "matched", 0.9)
    vm = CockpitViewModel(graph=g)
    result = vm.select_node("a")
    assert "node" in result
    assert result["node"]["node_type"] == "audio"
    assert len(result["neighbors"]) == 1
    assert result["neighbors"][0]["target"] == "b"
    assert vm.selected_node == "a"


def test_select_unknown_node_returns_error():
    vm = CockpitViewModel()
    result = vm.select_node("ghost")
    assert result.get("error") == "node_not_found"
    assert vm.selected_node is None


def test_stats():
    g = GraphService()
    g.add_node("a", "audio", "A")
    g.add_node("b", "audio", "B")
    g.add_edge("a", "b", "x", 0.5)
    vm = CockpitViewModel(graph=g)
    assert vm.stats()["n_nodes"] == 2
    assert vm.stats()["n_edges"] == 1
