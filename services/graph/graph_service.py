"""D-023 P3: Graph-Service (NetworkX-basiert).

In-Memory-Graph mit Add-Node/Edge-API. Wird vom Sigma.js-Frontend
(via QWebEngineView) und vom Pacing-Memory v2 als Strukturquelle genutzt.

DB-Persistenz (graph_node, graph_edge SQL-Tabellen) ist Phase-2;
diese Klasse ist die produktive in-memory Reference.
"""
from __future__ import annotations

from typing import Any, Iterable

import networkx as nx
import numpy as np

from services.graph.knn_backend import KnnBackend, pick_backend_strategy

EPS = 1e-9


class GraphService:
    def __init__(self) -> None:
        self._g = nx.DiGraph()

    # ── Nodes ──────────────────────────────────────────────────────────────

    def add_node(self, node_id: str, node_type: str, title: str, **attrs: Any) -> None:
        self._g.add_node(node_id, node_type=node_type, title=title, **attrs)

    def has_node(self, node_id: str) -> bool:
        return self._g.has_node(node_id)

    def get_node(self, node_id: str) -> dict[str, Any]:
        if not self.has_node(node_id):
            raise KeyError(node_id)
        return dict(self._g.nodes[node_id])

    def node_count(self) -> int:
        return int(self._g.number_of_nodes())

    # ── Edges ──────────────────────────────────────────────────────────────

    def add_edge(self, source: str, target: str, edge_type: str, weight: float, **attrs: Any) -> None:
        if not (self.has_node(source) and self.has_node(target)):
            raise KeyError(f"{source} or {target} not in graph")
        self._g.add_edge(source, target, edge_type=edge_type, weight=float(weight), **attrs)

    def has_edge(self, source: str, target: str) -> bool:
        return self._g.has_edge(source, target)

    def get_edge(self, source: str, target: str) -> dict[str, Any]:
        if not self.has_edge(source, target):
            raise KeyError(f"({source}, {target}) not in graph")
        return dict(self._g[source][target])

    def edge_count(self) -> int:
        return int(self._g.number_of_edges())

    # ── Queries ────────────────────────────────────────────────────────────

    def neighbors(self, node_id: str, edge_type: str | None = None) -> list[dict[str, Any]]:
        if not self.has_node(node_id):
            raise KeyError(node_id)
        out = []
        for tgt in self._g.successors(node_id):
            data = self._g[node_id][tgt]
            if edge_type is not None and data.get("edge_type") != edge_type:
                continue
            out.append({"target": tgt, **data})
        return out

    def top_k_neighbors(self, node_id: str, k: int = 5, edge_type: str | None = None) -> list[dict[str, Any]]:
        ns = self.neighbors(node_id, edge_type=edge_type)
        ns.sort(key=lambda x: x.get("weight", 0.0), reverse=True)
        return ns[:k]

    # ── Bulk ───────────────────────────────────────────────────────────────

    def build_similarity_edges(
        self,
        node_ids: Iterable[str],
        embeddings: np.ndarray,
        k: int = 5,
        min_similarity: float = 0.5,
        edge_type: str = "similar",
    ) -> int:
        """Berechnet k-NN über Embeddings, fügt Top-K-Kanten ein. Self-Edges
        werden ausgelassen.

        Returns:
            Anzahl hinzugefügter Edges.
        """
        ids = list(node_ids)
        if len(ids) != embeddings.shape[0]:
            raise ValueError("len(node_ids) muss embeddings.shape[0] entsprechen")
        # Wähle Backend (D-025)
        strategy = pick_backend_strategy(n_items=len(ids))
        backend = KnnBackend(strategy=strategy)
        backend.fit(embeddings)
        # k+1 weil Self-Match meist erster ist
        dists, idxs = backend.query(embeddings, k=min(k + 1, len(ids)))
        edges_added = 0
        for i, nid in enumerate(ids):
            for j in range(idxs.shape[1]):
                target_idx = int(idxs[i, j])
                if target_idx == i:
                    continue  # skip self
                similarity = 1.0 - float(dists[i, j])
                if similarity < min_similarity:
                    continue
                target_id = ids[target_idx]
                self.add_edge(nid, target_id, edge_type, weight=similarity)
                edges_added += 1
        return edges_added

    # ── Export ─────────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Sigma.js-kompatibles Dict (nodes + edges-Liste)."""
        return {
            "nodes": [
                {"id": n, **dict(self._g.nodes[n])}
                for n in self._g.nodes
            ],
            "edges": [
                {"source": s, "target": t, **dict(self._g[s][t])}
                for s, t in self._g.edges
            ],
        }
