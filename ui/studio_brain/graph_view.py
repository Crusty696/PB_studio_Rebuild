"""GraphView — Structure tab Graph mode (T10.2d).

Force-directed compat-graph view. Read-only display of nodes (enriched
scenes) and edges (struct_compat_edge cosine-similarity pairs). Clicking
a node emits ``clipSelected(scene_id)`` so the Structure tab's Inspector
can listen.

Design choices
--------------
- Layout engine: ``networkx.spring_layout`` with ``seed=42, iterations=50``.
  Seeded for reproducibility across sessions (Feasibility §R5: stable layout
  is nice for the user and essential for deterministic tests).
- Layout caching: positions are keyed by a fingerprint
  ``(frozenset(node_ids), frozenset((a,b) for edges))``. Unless topology
  changes, the cached positions dict is returned by reference so a fresh
  ``render_graph()`` never recomputes.
- Auto-fallback: if ``scene_count > _GRAPH_FALLBACK_THRESHOLD`` (2000,
  Feasibility §R5), the widget refuses to compute a layout and emits
  ``fellBackToGrid(reason)``. The parent (Structure tab) listens and
  swaps the stacked-widget index back to Grid.
"""

from __future__ import annotations

import copy
import logging
from typing import Optional

import networkx as nx
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsView,
    QWidget,
)

from services.brain_service import BrainService
from ui.studio_brain.structure_tab import _bucket_color

logger = logging.getLogger(__name__)


# Feasibility §R5: spring_layout on a graph of > ~2000 nodes is no longer
# interactive — we fall back to Grid mode above this threshold. A module
# constant (not a class attribute) is the cleaner seam here because the
# threshold is a feasibility-document invariant, not a per-instance tunable.
_GRAPH_FALLBACK_THRESHOLD: int = 2000

# Multiplier turning the unit-square spring_layout output into a scene-sized
# bounding box. 1500 gives ~3000×3000 world coordinates centred on origin.
_WORLD_SCALE: float = 1500.0

# Node diameter (px in scene coordinates). Kept small so the view can
# accommodate a few hundred nodes without the edges becoming invisible.
_NODE_DIAMETER: float = 14.0


# ── Custom items ──────────────────────────────────────────────────────────────


class _NodeItem(QGraphicsEllipseItem):
    """QGraphicsEllipseItem carrying its scene_id for click-dispatch.

    We intentionally do NOT override ``mousePressEvent`` here — the surrounding
    ``GraphView`` routes mouse clicks via ``itemAt`` so the drag-pan mode
    doesn't swallow node clicks.
    """

    def __init__(
        self,
        scene_id: int,
        bucket_id: Optional[int],
        x: float,
        y: float,
        parent: Optional[QGraphicsEllipseItem] = None,
    ) -> None:
        r = _NODE_DIAMETER / 2.0
        super().__init__(QRectF(-r, -r, _NODE_DIAMETER, _NODE_DIAMETER), parent)
        self.setPos(x, y)
        self._scene_id = int(scene_id)
        self._bucket_id = bucket_id
        self._base_pen = QPen(QColor("#1f2530"), 1.0)
        self._highlight_pen = QPen(QColor("#d4a44a"), 2.5)
        self.setPen(self._base_pen)
        self.setBrush(QBrush(_bucket_color(bucket_id)))
        self.setAcceptHoverEvents(False)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable, False)

    @property
    def scene_id(self) -> int:
        return self._scene_id

    def set_highlighted(self, on: bool) -> None:
        self.setPen(self._highlight_pen if on else self._base_pen)


# ── Main widget ───────────────────────────────────────────────────────────────


class GraphView(QGraphicsView):
    """Force-directed compat-graph view.

    Read-only display; clicking a node emits ``clipSelected(scene_id)``.
    If the scene count exceeds ``_GRAPH_FALLBACK_THRESHOLD``, ``render_graph``
    refuses to build and emits ``fellBackToGrid(reason)``.
    """

    clipSelected = Signal(int)
    fellBackToGrid = Signal(str)

    def __init__(
        self,
        brain_service: BrainService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._svc = brain_service

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setBackgroundBrush(QBrush(QColor("#0c1118")))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Per-view state.
        self._node_items: dict[int, _NodeItem] = {}
        self._edge_items: list[QGraphicsLineItem] = []
        # Layout cache: fingerprint -> dict[scene_id, (x, y)].
        self._layout_cache: dict[
            tuple[frozenset[int], frozenset[tuple[int, int]]],
            dict[int, tuple[float, float]],
        ] = {}
        # The positions dict actually in use (reference — NOT a copy — when the
        # fingerprint hits cache). Exposed for tests via ``current_positions``.
        self._positions: Optional[dict[int, tuple[float, float]]] = None

    # ── public API ────────────────────────────────────────────────────────────
    def render_graph(self) -> bool:
        """Read fresh data, (re)compute spring_layout, rebuild the scene.

        Returns
        -------
        bool
            ``True`` if the graph was rendered, ``False`` if the fallback
            fired because ``scene_count > _GRAPH_FALLBACK_THRESHOLD``.
        """
        self._svc.invalidate()
        snapshot = self._svc.graph_nodes_and_edges()
        nodes = snapshot["nodes"]
        edges = snapshot["edges"]
        scene_count = int(snapshot["scene_count"])

        if scene_count > _GRAPH_FALLBACK_THRESHOLD:
            reason = (
                f"Too many scenes ({scene_count} > {_GRAPH_FALLBACK_THRESHOLD}) "
                f"— showing Grid instead"
            )
            logger.info("GraphView: %s", reason)
            self.fellBackToGrid.emit(reason)
            return False

        positions = self._compute_or_reuse_layout(nodes, edges)
        self._rebuild_scene(nodes, edges, positions)
        return True

    def set_active_scene(self, scene_id: int) -> None:
        """Pan the view to the node with this ``scene_id`` (if any) and
        highlight it. Other nodes are de-highlighted."""
        target = self._node_items.get(int(scene_id))
        for item in self._node_items.values():
            item.set_highlighted(item is target)
        if target is not None:
            self.centerOn(target)

    def clear(self) -> None:
        """Drop all items from the scene and forget the positions reference.
        Does NOT clear the layout cache — the same graph can be re-rendered
        cheaply afterwards."""
        self._scene.clear()
        self._node_items.clear()
        self._edge_items.clear()
        self._positions = None

    # ── test-introspection helpers ────────────────────────────────────────────
    def current_positions(self) -> Optional[dict[int, tuple[float, float]]]:
        """Return the positions dict currently rendered (by reference).

        Used by tests to assert cache-reuse semantics. ``None`` until the
        first successful ``render_graph`` call.
        """
        return self._positions

    def node_items(self) -> dict[int, _NodeItem]:
        return dict(self._node_items)

    def edge_items(self) -> list[QGraphicsLineItem]:
        return list(self._edge_items)

    def _emit_click_for_scene(self, scene_id: int) -> None:
        """Test-only hook: synthesise a node click without an actual mouse
        event. Kept as a thin wrapper around the same signal the real
        ``mousePressEvent`` path emits, so tests exercise the same contract.
        """
        self.clipSelected.emit(int(scene_id))

    # ── layout + scene construction ───────────────────────────────────────────
    @staticmethod
    def _fingerprint(
        nodes: list[dict], edges: list[dict]
    ) -> tuple[frozenset[int], frozenset[tuple[int, int]]]:
        node_ids = frozenset(int(n["scene_id"]) for n in nodes)
        edge_pairs = frozenset(
            (int(e["a"]), int(e["b"])) for e in edges
        )
        return (node_ids, edge_pairs)

    def _compute_or_reuse_layout(
        self, nodes: list[dict], edges: list[dict]
    ) -> dict[int, tuple[float, float]]:
        fp = self._fingerprint(nodes, edges)
        cached = self._layout_cache.get(fp)
        if cached is not None:
            self._positions = cached
            return cached

        g: nx.Graph = nx.Graph()
        for n in nodes:
            g.add_node(int(n["scene_id"]))
        for e in edges:
            g.add_edge(
                int(e["a"]),
                int(e["b"]),
                weight=float(e.get("similarity") or 0.0),
            )

        if g.number_of_nodes() == 0:
            positions: dict[int, tuple[float, float]] = {}
        else:
            raw = nx.spring_layout(g, seed=42, iterations=50)
            positions = {
                int(sid): (
                    float(xy[0]) * _WORLD_SCALE,
                    float(xy[1]) * _WORLD_SCALE,
                )
                for sid, xy in raw.items()
            }

        self._layout_cache[fp] = positions
        self._positions = positions
        return positions

    def _rebuild_scene(
        self,
        nodes: list[dict],
        edges: list[dict],
        positions: dict[int, tuple[float, float]],
    ) -> None:
        self._scene.clear()
        self._node_items.clear()
        self._edge_items.clear()

        # Edges first, so nodes render on top of their lines.
        for e in edges:
            a, b = int(e["a"]), int(e["b"])
            pa = positions.get(a)
            pb = positions.get(b)
            if pa is None or pb is None:
                continue
            sim = float(e.get("similarity") or 0.0)
            # Clamp alpha to [0.1, 0.7] — faint for weak edges, still readable
            # for strong ones but never a solid block.
            alpha_f = max(0.1, min(0.7, sim))
            color = QColor("#9ca3af")
            color.setAlphaF(alpha_f)
            pen = QPen(color, 1.0)
            line = QGraphicsLineItem(pa[0], pa[1], pb[0], pb[1])
            line.setPen(pen)
            line.setZValue(-1.0)
            self._scene.addItem(line)
            self._edge_items.append(line)

        for n in nodes:
            sid = int(n["scene_id"])
            pos = positions.get(sid)
            if pos is None:
                continue
            item = _NodeItem(
                scene_id=sid,
                bucket_id=n.get("style_bucket_id"),
                x=pos[0],
                y=pos[1],
            )
            item.setZValue(0.0)
            item.setToolTip(
                f"#{sid}  role={n.get('role') or '—'}  "
                f"mood={n.get('mood_refined') or '—'}"
            )
            self._scene.addItem(item)
            self._node_items[sid] = item

        # Recompute scene bounding rect so the view can fit it on demand.
        self._scene.setSceneRect(self._scene.itemsBoundingRect())

    # ── interaction ───────────────────────────────────────────────────────────
    def mousePressEvent(self, event) -> None:  # noqa: N802 — Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            item = self._scene.itemAt(scene_pos, self.transform())
            node = self._resolve_node_item(item)
            if node is not None:
                self.clipSelected.emit(node.scene_id)
                event.accept()
                return
        super().mousePressEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802 — Qt override
        # Simple zoom: scroll up = zoom in (1.15x), scroll down = 1/1.15.
        if event.angleDelta().y() == 0:
            super().wheelEvent(event)
            return
        factor = 1.15 if event.angleDelta().y() > 0 else (1.0 / 1.15)
        self.scale(factor, factor)

    @staticmethod
    def _resolve_node_item(item) -> Optional[_NodeItem]:
        """Walk up a QGraphicsItem parent chain to the nearest _NodeItem."""
        cur = item
        while cur is not None:
            if isinstance(cur, _NodeItem):
                return cur
            cur = cur.parentItem()
        return None


# Re-export for tests + the structure tab.
__all__ = [
    "GraphView",
    "_GRAPH_FALLBACK_THRESHOLD",
    "_WORLD_SCALE",
]


def _copy_positions_for_test(
    positions: dict[int, tuple[float, float]]
) -> dict[int, tuple[float, float]]:
    """Deep-copy helper exposed to tests so they can compare snapshots
    across renders without the live dict being mutated under them.
    """
    return copy.deepcopy(positions)
