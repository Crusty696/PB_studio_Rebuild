"""D-023 P1: Sigma.js HTML-Renderer.

Produziert ein eigenständiges HTML-Dokument (CDN-Sigma + Graphology +
ForceAtlas2), das via QWebEngineView in das Director's-Cockpit-Tab
geladen wird.

Trennt Layout-Logik (Python) von Sigma-Rendering (JS): build_sigma_payload
liefert pure Daten, render_sigma_html embedded sie.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from services.graph.graph_service import GraphService

# Type → Color (frei wählbare Default-Palette)
_TYPE_COLOR: dict[str, str] = {
    "audio": "#4A90E2",      # blau
    "video": "#7ED321",      # grün
    "project": "#F5A623",    # orange
    "section": "#BD10E0",    # lila
    "scene": "#50E3C2",      # türkis
    "default": "#9B9B9B",    # grau
}


def _color_for_type(node_type: str) -> str:
    return _TYPE_COLOR.get(node_type, _TYPE_COLOR["default"])


def _stable_position(node_id: str) -> tuple[float, float]:
    """Deterministische Pseudo-Position auf Einheits-Quadrat ums Zentrum.
    Wird vom JS-ForceAtlas2 ohnehin überschrieben — dient nur als Init.

    B-037: SHA1 ist hier KEIN Sicherheits-Hash — nur deterministisches
    Layout-Mapping ``node_id -> (x, y)``. ``usedforsecurity=False``
    macht das fuer Bandit/CWE-327 explizit.
    """
    h = int(
        hashlib.sha1(node_id.encode("utf-8"), usedforsecurity=False).hexdigest(),
        16,
    )
    angle = (h % 360) * math.pi / 180.0
    radius = ((h // 360) % 100) / 100.0
    return float(math.cos(angle) * radius), float(math.sin(angle) * radius)


# ---------------------------------------------------------------------------
# B-719: CDN-Einbindung mit gepinnter Subresource-Integrity.
#
# graphology + sigma kommen weiterhin von cdn.jsdelivr.net (im Repo liegen
# keine gevendorten Bundles, und Herunterladen ist hier nicht erlaubt).
# Ohne ``integrity`` konnte ein manipuliertes/ausgetauschtes CDN-Bundle
# beliebiges JS in die QWebEngineView einschleusen.
#
# Die SRI-Hashes wurden am 2026-07-27 aus zwei unabhaengigen Quellen
# desselben npm-Artefakts ermittelt und stimmen byte-genau ueberein:
#   cdn.jsdelivr.net/npm/... und unpkg.com/...
#   graphology@0.25.4 dist/graphology.umd.min.js  -> 74221 Bytes
#   sigma@3.0.0-beta.18 dist/sigma.min.js         -> 146211 Bytes
_GRAPHOLOGY_URL = (
    "https://cdn.jsdelivr.net/npm/graphology@0.25.4/dist/graphology.umd.min.js"
)
_GRAPHOLOGY_SRI = "sha384-643a1dipBp0OHFnm3WeZmMnuJ+ZY/MEll1vTGCjeFzkB/RySh+Almy3Ffn+sxO7y"
_SIGMA_URL = "https://cdn.jsdelivr.net/npm/sigma@3.0.0-beta.18/dist/sigma.min.js"
_SIGMA_SRI = "sha384-ju18EgXgALUsS1bX3JDtc5emeKWD585Ix2AE/QhmDn+O+G57LhK8+ZfG6K8zo9G4"


def _json_for_script(obj: Any) -> str:
    """B-719: JSON so serialisieren, dass es in einem ``<script>``-Kontext
    sicher ist.

    ``json.dumps`` allein reicht nicht: ein Node-Label wie
    ``</script><script>...`` beendet den Script-Block des HTML-Parsers und
    fuehrt eigenes JS aus (Labels stammen aus Datei-/Projektnamen, also aus
    nicht-vertrauenswuerdiger Eingabe).

    Escaped werden:
      * ``<``/``>``/``&`` -> ``\\u003c``/``\\u003e``/``\\u0026``
        (verhindert ``</script>``-Ausbruch und HTML-Entity-Tricks)
      * U+2028 / U+2029 -> ``\\u2028``/``\\u2029``
        (sind in JS-Stringliteralen vor ES2019 harte Zeilenumbrueche)
    Das Ergebnis bleibt gueltiges JSON und deserialisiert identisch.
    """
    raw = json.dumps(obj, ensure_ascii=False)
    return (
        raw.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def build_sigma_payload(graph: GraphService) -> dict[str, Any]:
    """Konvertiert GraphService → Sigma-kompatibles Dict."""
    raw = graph.to_dict()
    nodes = []
    for n in raw["nodes"]:
        node_id = str(n["id"])
        x, y = _stable_position(node_id)
        nodes.append({
            "id": node_id,
            "label": str(n.get("title", node_id)),
            "node_type": n.get("node_type", "default"),
            "x": x,
            "y": y,
            "size": float(n.get("size", 6.0)),
            "color": _color_for_type(n.get("node_type", "default")),
        })
    edges = []
    for i, e in enumerate(raw["edges"]):
        edges.append({
            "id": f"e{i}",
            "source": str(e["source"]),
            "target": str(e["target"]),
            "size": max(0.5, float(e.get("weight", 0.5)) * 4.0),
            "edge_type": e.get("edge_type", "related"),
        })
    return {"nodes": nodes, "edges": edges}


_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>PB Studio — Graph Director's Cockpit</title>
<style>
  body {{ margin: 0; padding: 0; background: #1a1a1a; color: #eee;
          font-family: -apple-system, system-ui, Segoe UI, Arial, sans-serif; }}
  #container {{ position: absolute; top: 0; left: 0; right: 0; bottom: 0; }}
  #info {{ position: absolute; top: 8px; left: 8px;
           background: rgba(0,0,0,.6); padding: 6px 10px; border-radius: 4px; }}
  #load-error {{ position: absolute; top: 50%; left: 50%;
                 transform: translate(-50%, -50%); max-width: 640px;
                 background: #2b1d1d; border: 1px solid #a04040;
                 border-radius: 6px; padding: 16px 20px; line-height: 1.5;
                 font-size: 13px; white-space: pre-wrap; }}
</style>
<script src="{graphology_url}"
        integrity="{graphology_sri}"
        crossorigin="anonymous" referrerpolicy="no-referrer"></script>
<script src="{sigma_url}"
        integrity="{sigma_sri}"
        crossorigin="anonymous" referrerpolicy="no-referrer"></script>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
</head>
<body>
<div id="info">PB Studio Graph — {n_nodes} Nodes, {n_edges} Edges</div>
<div id="container"></div>
<script>
(function () {{
  // B-719: Fehlerpanel statt leerem Tab. Text wird per textContent gesetzt,
  // damit hier nichts injizierbar ist.
  function showLoadError(msg) {{
    const info = document.getElementById('info');
    const container = document.getElementById('container');
    if (info) {{ info.textContent = 'PB Studio Graph — nicht geladen'; }}
    if (!container) {{ return; }}
    container.textContent = '';
    const box = document.createElement('div');
    box.id = 'load-error';
    box.textContent = msg;
    container.appendChild(box);
  }}

  // B-719: graphology/sigma kommen vom CDN und sind SRI-gepinnt. Offline —
  // oder wenn der Integrity-Check anschlaegt — laedt der Browser sie NICHT.
  // Vorher lief der Code trotzdem weiter und starb an `new graphology.Graph()`
  // -> Graph-Tab blieb kommentarlos leer. Jetzt: sichtbare Meldung.
  const missing = [];
  if (typeof graphology === "undefined") {{ missing.push("graphology"); }}
  if (!(window.Sigma || window.sigma)) {{ missing.push("sigma"); }}
  if (missing.length > 0) {{
    showLoadError(
      "Graph-Bibliotheken konnten nicht geladen werden: " + missing.join(", ") + ".\\n\\n"
      + "PB Studio laedt graphology und sigma von cdn.jsdelivr.net. Ohne "
      + "Internetverbindung — oder wenn die ausgelieferten Dateien nicht mehr "
      + "zur gepinnten Subresource-Integrity passen — bleibt der Graph leer.\\n\\n"
      + "Pruefen: Internetverbindung, Proxy/Firewall, sowie die SRI-Pins in "
      + "services/graph/sigma_renderer.py."
    );
    return;
  }}

  const PAYLOAD = {payload_json};
  const G = new graphology.Graph();
  PAYLOAD.nodes.forEach(n => {{
    G.addNode(n.id, {{
      label: n.label, x: n.x, y: n.y, size: n.size, color: n.color, type: 'circle'
    }});
  }});
  PAYLOAD.edges.forEach(e => {{
    if (G.hasNode(e.source) && G.hasNode(e.target)) {{
      G.addEdge(e.source, e.target, {{ size: e.size }});
    }}
  }});
  // Optional ForceAtlas2 Layout. The pinned npm package has no browser UMD
  // bundle at the old /build path, so the graph must render without it.
  if (PAYLOAD.nodes.length > 0) {{
    const forceAtlas2 =
      window.graphologyLayoutForceatlas2 ||
      window.graphologyLayoutForceAtlas2;
    if (forceAtlas2 && typeof forceAtlas2.assign === "function") {{
      forceAtlas2.assign(G, {{ iterations: 50, settings: {{ gravity: 1.0 }} }});
    }} else {{
      // Keep deterministic fallback positions without Qt data-url log spam.
    }}
  }}
  const SigmaRenderer = window.Sigma || window.sigma;
  const renderer = new SigmaRenderer(G, document.getElementById('container'));

  // P0 #3: QWebChannel-Bridge — Klick auf Knoten ruft Python-Slot.
  // Wenn QtWebChannel nicht verfügbar (z.B. im normalen Browser oder
  // bei deaktiviertem WebChannel), bleibt der Click-Handler stumm.
  let pythonBridge = null;
  if (typeof QWebChannel !== "undefined" && typeof qt !== "undefined") {{
    new QWebChannel(qt.webChannelTransport, function(channel) {{
      pythonBridge = channel.objects.cockpitBridge;
    }});
  }}
  renderer.on("clickNode", function(event) {{
    const nodeId = event.node;
    if (pythonBridge && typeof pythonBridge.onNodeClicked === "function") {{
      pythonBridge.onNodeClicked(nodeId);
    }}
  }});
}})();
</script>
</body>
</html>
"""


def render_sigma_html(graph: GraphService) -> str:
    """Liefert komplettes HTML-Dokument."""
    payload = build_sigma_payload(graph)
    return _HTML_TEMPLATE.format(
        n_nodes=len(payload["nodes"]),
        n_edges=len(payload["edges"]),
        # B-719: script-kontext-sicheres JSON statt rohem json.dumps.
        payload_json=_json_for_script(payload),
        graphology_url=_GRAPHOLOGY_URL,
        graphology_sri=_GRAPHOLOGY_SRI,
        sigma_url=_SIGMA_URL,
        sigma_sri=_SIGMA_SRI,
    )
