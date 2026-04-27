"""D-023 P4: Director's-Cockpit-Graph-Tab View-Model (Logik-Layer).

Headless-Logik für das Cockpit-Tab. UI-Widget
(`ui/widgets/graph_cockpit_tab.py`) konsumiert dieses Model.

Gibt:
- Aktuelle GraphService-Instanz
- gerenderte Sigma-HTML
- click-handler-API: select_node(node_id) → details
- B-199 F-5: ``populate_from_brain_service(svc)`` laedt
  ``struct_clip_tags`` + ``struct_compat_edge`` in den in-memory
  GraphService. Vorher war der Cockpit-Tab leer.

Volle GUI-Verdrahtung (QWebEngineView + QWebChannel) ist Cycle-11-Task.
"""
from __future__ import annotations

import logging
from typing import Any

from services.graph.graph_service import GraphService
from services.graph.sigma_renderer import render_sigma_html

logger = logging.getLogger(__name__)


class CockpitViewModel:
    def __init__(self, graph: GraphService | None = None):
        self._graph = graph or GraphService()
        self._selected_node: str | None = None
        # B-199 F-5: optionale Daten-Quelle fuer Refresh-Button.
        self._brain_service: Any | None = None

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

    # ── B-199 F-5: Daten-Loader ────────────────────────────────────────────

    def set_data_source(self, brain_service: Any) -> None:
        """B-199 F-5: Merkt sich den BrainService fuer ``refresh_data()``-
        Aufrufe (Refresh-Button im Cockpit-Tab). Wer den Tab nur einmalig
        befuellt, braucht das nicht.
        """
        self._brain_service = brain_service

    def refresh_data(self) -> dict[str, int]:
        """B-199 F-5: Reload aus der gemerkten Daten-Quelle.

        Returns:
            Same shape wie ``populate_from_brain_service``, oder
            ``{"nodes": 0, "edges": 0, "scene_count": 0}`` wenn keine
            Daten-Quelle gesetzt war.
        """
        if self._brain_service is None:
            return {"nodes": 0, "edges": 0, "scene_count": 0}
        return self.populate_from_brain_service(self._brain_service)

    def populate_from_brain_service(self, brain_service: Any) -> dict[str, int]:
        """B-199 F-5: Befuellt den in-memory GraphService aus dem
        Snapshot von ``BrainService.graph_nodes_and_edges()``.

        Vorher war der Cockpit-Tab leer (Source-Kommentar in
        ``graph_service.py:6`` sagte: *"DB-Persistenz ist Phase-2"*).
        Diese Methode ist die Phase-2-Bruecke ohne neue SQL-Tabellen:
        wir lesen direkt aus ``struct_clip_tags`` /
        ``struct_compat_edge`` (was ``BrainService`` bereits aggregiert)
        und uebersetzen das in ``GraphService.add_node`` /
        ``add_edge``-Aufrufe.

        Returns:
            ``{"nodes": n, "edges": m, "scene_count": k}`` — Counts
            nach dem Load (oder ``{"error": ...}`` bei Failure).

        Idempotent: ein bereits gefuellter Graph wird durch einen
        frischen ersetzt (alte Knoten und Kanten werden verworfen).
        Tests duerfen via Mock-BrainService eigene Daten injizieren.
        """
        try:
            snapshot = brain_service.graph_nodes_and_edges()
        except Exception as exc:  # broad: UI darf nicht crashen
            logger.warning(
                "B-199 F-5: graph_nodes_and_edges() fehlgeschlagen: %s", exc
            )
            return {"error": str(exc), "nodes": 0, "edges": 0}

        # Frischer Graph — vermeidet Duplikate bei mehrfachem Refresh.
        new_graph = GraphService()

        for node in snapshot.get("nodes", []):
            try:
                node_id = f"scene-{int(node['scene_id'])}"
                title = (
                    node.get("style_bucket_name")
                    or f"Scene {node['scene_id']}"
                )
                new_graph.add_node(
                    node_id=node_id,
                    node_type="scene",
                    title=str(title),
                    role=node.get("role"),
                    mood_refined=node.get("mood_refined"),
                    style_bucket_id=node.get("style_bucket_id"),
                    style_bucket_name=node.get("style_bucket_name"),
                )
            except (KeyError, TypeError, ValueError) as exc:
                logger.debug("B-199 F-5: skip invalid node %s: %s", node, exc)

        for edge in snapshot.get("edges", []):
            try:
                a_id = f"scene-{int(edge['a'])}"
                b_id = f"scene-{int(edge['b'])}"
                similarity = float(edge.get("similarity") or 0.0)
                # ``BrainService.graph_nodes_and_edges`` deduped Kanten
                # bereits via ``MIN/MAX``. Wir adden zwei gerichtete
                # Kanten (a→b + b→a) damit ``top_k_neighbors`` aus
                # beiden Richtungen funktioniert.
                if new_graph.has_node(a_id) and new_graph.has_node(b_id):
                    new_graph.add_edge(
                        source=a_id,
                        target=b_id,
                        edge_type="similar",
                        weight=similarity,
                    )
                    new_graph.add_edge(
                        source=b_id,
                        target=a_id,
                        edge_type="similar",
                        weight=similarity,
                    )
            except (KeyError, TypeError, ValueError) as exc:
                logger.debug("B-199 F-5: skip invalid edge %s: %s", edge, exc)

        # Atomarer Swap.
        self._graph = new_graph
        self._selected_node = None  # Auswahl kann auf entfernten Node zeigen.

        result = {
            "nodes": new_graph.node_count(),
            "edges": new_graph.edge_count(),
            "scene_count": int(snapshot.get("scene_count", 0)),
        }
        logger.info(
            "B-199 F-5: Cockpit-Graph populated — %d Knoten, %d Kanten "
            "(scene_count=%d)",
            result["nodes"], result["edges"], result["scene_count"],
        )
        return result
