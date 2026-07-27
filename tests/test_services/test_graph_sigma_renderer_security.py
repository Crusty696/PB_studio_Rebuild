"""B-719: Sigma-Renderer — Script-Kontext-Escaping + abgesicherte CDN-Einbindung."""
from __future__ import annotations

import json
import re

from services.graph.graph_service import GraphService
from services.graph.sigma_renderer import (
    _GRAPHOLOGY_SRI,
    _GRAPHOLOGY_URL,
    _SIGMA_SRI,
    _SIGMA_URL,
    render_sigma_html,
)

_PAYLOAD_RE = re.compile(r"^\s*const PAYLOAD = (.*);\s*$", re.MULTILINE)


def _extract_payload(html: str) -> dict:
    match = _PAYLOAD_RE.search(html)
    assert match, "const PAYLOAD = ... nicht gefunden"
    return json.loads(match.group(1))


def test_node_label_cannot_break_out_of_script_block():
    """Ein Label mit ``</script>`` darf den Script-Block nicht beenden."""
    evil = '</script><script>window.__pwned = 1;</script>'
    g = GraphService()
    g.add_node("a", "audio", evil)

    html = render_sigma_html(g)

    # Das Label darf keine zusaetzlichen Script-Grenzen erzeugen. Das Template
    # hat genau 4 <script>-Bloecke (graphology, sigma, qwebchannel, main).
    baseline = render_sigma_html(GraphService())
    assert html.count("</script>") == baseline.count("</script>") == 4
    assert "</script><script>" not in html
    # Stattdessen als JSON-Unicode-Escape.
    assert "\\u003c/script\\u003e" in html
    # Und der Payload deserialisiert weiterhin verlustfrei.
    payload = _extract_payload(html)
    assert payload["nodes"][0]["label"] == evil


def test_line_separator_in_label_is_escaped():
    """U+2028/U+2029 sind in JS-Stringliteralen harte Zeilenumbrueche."""
    g = GraphService()
    g.add_node("a", "audio", "Track\u2028A\u2029B")

    html = render_sigma_html(g)

    assert "\u2028" not in html
    assert "\u2029" not in html
    payload = _extract_payload(html)
    assert payload["nodes"][0]["label"] == "Track\u2028A\u2029B"


def test_cdn_scripts_carry_pinned_integrity_and_crossorigin():
    g = GraphService()
    g.add_node("a", "audio", "A")

    html = render_sigma_html(g)

    for url, sri in ((_GRAPHOLOGY_URL, _GRAPHOLOGY_SRI), (_SIGMA_URL, _SIGMA_SRI)):
        assert url in html
        assert sri.startswith("sha384-")
        assert f'integrity="{sri}"' in html
    # SRI auf klassischen Scripts erfordert CORS.
    assert html.count('crossorigin="anonymous"') >= 2


def test_missing_cdn_libraries_render_visible_error_instead_of_blank_tab():
    g = GraphService()
    g.add_node("a", "audio", "A")

    html = render_sigma_html(g)

    assert "function showLoadError(" in html
    assert 'missing.push("graphology")' in html
    assert 'missing.push("sigma")' in html
    assert "Graph-Bibliotheken konnten nicht geladen werden" in html
    # Fehlertext wird per textContent gesetzt (nicht injizierbar).
    assert "box.textContent = msg;" in html
    # Und der Renderer-Code wird uebersprungen statt an graphology zu sterben.
    assert "if (missing.length > 0) {" in html
