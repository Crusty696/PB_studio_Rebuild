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
</style>
<script src="https://cdn.jsdelivr.net/npm/graphology@0.25.4/dist/graphology.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/sigma@3.0.0-beta.18/dist/sigma.min.js"></script>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
</head>
<body>
<div id="info">PB Studio Graph — {n_nodes} Nodes, {n_edges} Edges</div>
<div id="container"></div>
<script>
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
        payload_json=json.dumps(payload, ensure_ascii=False),
    )
