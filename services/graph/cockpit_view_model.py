"""D-023 P4: Director's-Cockpit-Graph-Tab View-Model (Logik-Layer).

Headless-Logik für das Cockpit-Tab. UI-Widget
(`ui/widgets/graph_cockpit_tab.py`) konsumiert dieses Model.

Gibt:
- Aktuelle GraphService-Instanz
- gerenderte Sigma-HTML
- click-handler-API: select_node(node_id) → details

Volle GUI-Verdrahtung (QWebEngineView + QWebChannel) ist Cycle-11-Task.
"""
from __future__ import annotations

from typing import Any

from services.graph.graph_service import GraphService
from services.graph.sigma_renderer import render_sigma_html


class CockpitViewModel:
    def __init__(self, graph: GraphService | None = None):
        self._graph = graph or GraphService()
        self._selected_node: str | None = None

    @property
    def graph(self) -> GraphService:
        return self._graph

    def render_html(self) -> str:
        return render_sigma_html(self._graph)

    def select_node(self, node_id: str) -> dict[str, Any]:
        if not self._graph.has_node(node_id):
            return {"error": "node_not_found", "node_id": node_id}
        self._selected_node = node_id
        return {
            "node": self._graph.get_node(node_id),
            "neighbors": self._graph.top_k_neighbors(node_id, k=5),
        }

    @property
    def selected_node(self) -> str | None:
        return self._selected_node

    def stats(self) -> dict[str, int]:
        return {
            "n_nodes": self._graph.node_count(),
            "n_edges": self._graph.edge_count(),
        }
