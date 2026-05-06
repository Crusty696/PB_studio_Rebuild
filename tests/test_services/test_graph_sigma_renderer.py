"""D-023 P1: Sigma.js Renderer (HTML-Generator)."""
import json

from services.graph.graph_service import GraphService
from services.graph.sigma_renderer import render_sigma_html, build_sigma_payload


def _small_graph():
    g = GraphService()
    g.add_node("a", "audio", "Track A")
    g.add_node("b", "video", "Clip B")
    g.add_node("c", "video", "Clip C")
    g.add_edge("a", "b", "matched", 0.8)
    g.add_edge("a", "c", "matched", 0.5)
    return g


def test_payload_has_nodes_and_edges():
    g = _small_graph()
    payload = build_sigma_payload(g)
    assert "nodes" in payload and "edges" in payload
    assert len(payload["nodes"]) == 3
    assert len(payload["edges"]) == 2


def test_payload_nodes_have_required_fields():
    g = _small_graph()
    payload = build_sigma_payload(g)
    for n in payload["nodes"]:
        assert "id" in n
        assert "label" in n
        # Sigma erwartet x, y für Layout
        assert "x" in n and "y" in n
        assert "size" in n
        assert "color" in n


def test_payload_edges_have_size_attr():
    g = _small_graph()
    payload = build_sigma_payload(g)
    for e in payload["edges"]:
        assert "id" in e
        assert "source" in e and "target" in e
        assert "size" in e


def test_render_sigma_html_contains_payload():
    g = _small_graph()
    html = render_sigma_html(g)
    assert "<html" in html.lower()
    assert "sigma" in html.lower()
    # JSON-Payload muss eingebettet sein
    assert "Track A" in html
    assert "Clip B" in html


def test_render_sigma_html_valid_json_block():
    g = _small_graph()
    html = render_sigma_html(g)
    # Extrahiere JSON-Block
    start = html.find('"nodes"')
    assert start > 0


def test_color_per_node_type():
    g = GraphService()
    g.add_node("a", "audio", "A")
    g.add_node("v", "video", "V")
    g.add_node("p", "project", "P")
    payload = build_sigma_payload(g)
    by_id = {n["id"]: n for n in payload["nodes"]}
    # Pro Type unterschiedliche Farbe
    types_seen = {by_id["a"]["color"], by_id["v"]["color"], by_id["p"]["color"]}
    assert len(types_seen) == 3


def test_render_handles_empty_graph():
    g = GraphService()
    html = render_sigma_html(g)
    assert "<html" in html.lower()


def test_render_does_not_depend_on_missing_forceatlas2_bundle():
    g = _small_graph()
    html = render_sigma_html(g)
    assert "graphology-layout-forceatlas2@0.10.1/build/" not in html
    assert "sigma@3.0.0-beta.18/build/sigma.min.js" not in html
    assert "sigma@3.0.0-beta.18/dist/sigma.min.js" in html
    assert "const SigmaRenderer = window.Sigma || window.sigma;" in html
    assert "const forceAtlas2 =" in html
    assert "typeof forceAtlas2.assign === \"function\"" in html
    assert "Keep deterministic fallback positions" in html
