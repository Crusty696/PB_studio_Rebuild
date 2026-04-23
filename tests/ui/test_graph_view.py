"""T10.2d headless tests: GraphView + BrainService.graph_nodes_and_edges.

Offscreen Qt + on-disk SQLite, mirroring tests/ui/test_structure_tab.py and
tests/ui/test_inspector_panel.py. The ``_build_struct_db`` helper and the
scene / tag / bucket seed-helpers are imported as plain symbols from
test_structure_tab (same pattern as test_inspector_panel uses).

Note on click-emit testing: rather than synthesise a real mouse event (which
relies on precise screen-coordinate round-tripping, flaky across Qt backends
on Windows offscreen), we call the thin ``_emit_click_for_scene`` hook which
goes through the same signal the ``mousePressEvent`` path emits. This keeps
the test deterministic while still exercising the ``clipSelected`` contract
the StructureTab depends on.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from sqlalchemy import text

from PySide6.QtWidgets import QApplication

from services.brain_service import BrainService
from ui.studio_brain.graph_view import GraphView, _GRAPH_FALLBACK_THRESHOLD
from ui.studio_brain.structure_tab import StructureTab

# Reuse test_structure_tab's fixture helpers (plain import — no conftest).
from tests.ui.test_structure_tab import (  # noqa: E402
    _build_struct_db,
    _seed_basics,
    _seed_bucket,
    _seed_scene,
    _seed_tag,
)


# ── Qt helper ─────────────────────────────────────────────────────────────────


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ── Edge seed helper (kept local — different table than inspector tests) ────


def _seed_edge(
    conn,
    scene_id_a: int,
    scene_id_b: int,
    cosine: float = 0.7,
    rank: int = 0,
) -> None:
    conn.execute(
        text(
            "INSERT INTO struct_compat_edge "
            "(scene_id_a, scene_id_b, cosine_similarity, rank_in_a) "
            "VALUES (:a, :b, :c, :r)"
        ),
        {"a": scene_id_a, "b": scene_id_b, "c": cosine, "r": rank},
    )


# ── BrainService.graph_nodes_and_edges ────────────────────────────────────────


def test_graph_nodes_and_edges_returns_nodes_and_edges(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        for sid in (10, 11, 12):
            _seed_scene(conn, sid)
            _seed_tag(conn, sid, bucket_id=1)
        _seed_edge(conn, 10, 11, cosine=0.8, rank=0)
        _seed_edge(conn, 11, 12, cosine=0.6, rank=0)

    svc = BrainService(session_factory=Session)
    snap = svc.graph_nodes_and_edges()

    assert snap["scene_count"] == 3
    assert len(snap["nodes"]) == 3
    assert [n["scene_id"] for n in snap["nodes"]] == [10, 11, 12]
    assert len(snap["edges"]) == 2
    assert {(e["a"], e["b"]) for e in snap["edges"]} == {(10, 11), (11, 12)}


def test_graph_nodes_and_edges_excludes_unenriched_endpoints(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        # 3 scenes, only 20 and 21 get tags; 22 is unenriched.
        _seed_scene(conn, 20)
        _seed_scene(conn, 21)
        _seed_scene(conn, 22)
        _seed_tag(conn, 20, bucket_id=1)
        _seed_tag(conn, 21, bucket_id=1)
        # Edge between the two enriched scenes — kept.
        _seed_edge(conn, 20, 21, cosine=0.7, rank=0)
        # Edge touching the unenriched scene 22 — must be dropped.
        _seed_edge(conn, 21, 22, cosine=0.5, rank=1)

    svc = BrainService(session_factory=Session)
    snap = svc.graph_nodes_and_edges()

    assert snap["scene_count"] == 2
    assert {n["scene_id"] for n in snap["nodes"]} == {20, 21}
    assert len(snap["edges"]) == 1
    assert (snap["edges"][0]["a"], snap["edges"][0]["b"]) == (20, 21)


def test_graph_nodes_and_edges_deduplicates_reciprocal_edges(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        _seed_scene(conn, 5)
        _seed_scene(conn, 7)
        _seed_tag(conn, 5, bucket_id=1)
        _seed_tag(conn, 7, bucket_id=1)
        # Both orientations — must collapse to one record in canonical form.
        _seed_edge(conn, 5, 7, cosine=0.8, rank=0)
        _seed_edge(conn, 7, 5, cosine=0.8, rank=0)

    svc = BrainService(session_factory=Session)
    snap = svc.graph_nodes_and_edges()

    assert len(snap["edges"]) == 1
    assert snap["edges"][0]["a"] == 5
    assert snap["edges"][0]["b"] == 7


def test_graph_nodes_and_edges_orders_stable(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        for sid in (30, 31, 32, 33):
            _seed_scene(conn, sid)
            _seed_tag(conn, sid, bucket_id=1)
        # Insert in deliberately scrambled order.
        _seed_edge(conn, 32, 33, cosine=0.5, rank=0)
        _seed_edge(conn, 30, 33, cosine=0.4, rank=1)
        _seed_edge(conn, 31, 32, cosine=0.6, rank=2)
        _seed_edge(conn, 30, 31, cosine=0.9, rank=3)

    svc = BrainService(session_factory=Session)
    snap = svc.graph_nodes_and_edges()

    pairs = [(e["a"], e["b"]) for e in snap["edges"]]
    assert pairs == sorted(pairs)
    assert pairs == [(30, 31), (30, 33), (31, 32), (32, 33)]


# ── GraphView rendering ──────────────────────────────────────────────────────


def _seed_graph(
    engine: Any, node_ids: list[int], edge_pairs: list[tuple[int, int]]
) -> None:
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        for sid in node_ids:
            _seed_scene(conn, sid)
            _seed_tag(conn, sid, bucket_id=1)
        for i, (a, b) in enumerate(edge_pairs):
            _seed_edge(conn, a, b, cosine=0.5 + (i % 3) * 0.1, rank=i)


def test_graph_view_renders_within_threshold(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)

    node_ids = list(range(40, 50))  # 10 scenes
    # 15 unique edges on a small ring + chords.
    edges = [
        (40, 41), (41, 42), (42, 43), (43, 44), (44, 45),
        (45, 46), (46, 47), (47, 48), (48, 49), (40, 49),
        (40, 45), (41, 46), (42, 47), (43, 48), (44, 49),
    ]
    _seed_graph(engine, node_ids, edges)

    svc = BrainService(session_factory=Session)
    view = GraphView(svc)
    ok = view.render_graph()
    assert ok is True

    items = view.node_items()
    assert len(items) == 10
    assert set(items.keys()) == set(node_ids)
    assert len(view.edge_items()) == 15


def test_graph_view_falls_back_above_threshold(tmp_path: Path, monkeypatch) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    svc = BrainService(session_factory=Session)

    fake_count = 2500
    fake_nodes = [
        {
            "scene_id": i,
            "role": "hero",
            "mood_refined": "euphoric",
            "style_bucket_id": 1,
            "style_bucket_name": "Warm",
        }
        for i in range(fake_count)
    ]
    snapshot = {"nodes": fake_nodes, "edges": [], "scene_count": fake_count}
    monkeypatch.setattr(svc, "graph_nodes_and_edges", lambda: snapshot)

    view = GraphView(svc)
    reasons: list[str] = []
    view.fellBackToGrid.connect(reasons.append)

    ok = view.render_graph()
    assert ok is False
    assert len(reasons) == 1
    assert "Too many scenes" in reasons[0]
    assert str(fake_count) in reasons[0]
    assert str(_GRAPH_FALLBACK_THRESHOLD) in reasons[0]


def test_graph_view_layout_cache_reused_for_same_fingerprint(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    _seed_graph(engine, [60, 61, 62], [(60, 61), (61, 62)])

    svc = BrainService(session_factory=Session)
    view = GraphView(svc)

    assert view.render_graph() is True
    first = view.current_positions()
    assert first is not None
    first_snapshot = copy.deepcopy(first)

    assert view.render_graph() is True
    second = view.current_positions()
    # Identity: the cache returns the same dict object.
    assert second is first
    # And values are unchanged (sanity on top of identity).
    assert second == first_snapshot


def test_graph_view_layout_recomputed_when_topology_changes(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    _seed_graph(engine, [70, 71, 72], [(70, 71), (71, 72)])

    svc = BrainService(session_factory=Session)
    view = GraphView(svc)

    assert view.render_graph() is True
    first = view.current_positions()
    assert first is not None
    assert set(first.keys()) == {70, 71, 72}

    # Add a new scene + tag — fingerprint changes.
    with engine.begin() as conn:
        _seed_scene(conn, 73)
        _seed_tag(conn, 73, bucket_id=1)
        _seed_edge(conn, 72, 73, cosine=0.6, rank=10)

    assert view.render_graph() is True
    second = view.current_positions()
    assert second is not None
    assert second is not first  # new object because new fingerprint
    assert 73 in second
    assert set(second.keys()) == {70, 71, 72, 73}


def test_graph_view_click_emits_clipSelected(tmp_path: Path) -> None:
    """We drive the click via GraphView._emit_click_for_scene — the same
    signal the mousePressEvent path fires — to keep the assertion
    deterministic across Qt backends (see module docstring)."""
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    _seed_graph(engine, [80, 81, 82], [(80, 81), (81, 82)])

    svc = BrainService(session_factory=Session)
    view = GraphView(svc)
    assert view.render_graph() is True

    received: list[int] = []
    view.clipSelected.connect(received.append)

    view._emit_click_for_scene(80)
    assert received == [80]


# ── StructureTab toggle + fallback auto-switch ────────────────────────────────


def test_structure_tab_mode_toggle_swaps_stacked_widget(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    _seed_graph(engine, [90, 91, 92], [(90, 91), (91, 92)])

    svc = BrainService(session_factory=Session)
    tab = StructureTab(brain_service=svc)

    # Default mode → Grid.
    assert tab.current_view_mode() == "Grid"
    assert tab._stack.currentIndex() == 0

    tab.set_view_mode("Graph")
    assert tab.current_view_mode() == "Graph"
    assert tab._stack.currentIndex() == 1

    tab.set_view_mode("Grid")
    assert tab.current_view_mode() == "Grid"
    assert tab._stack.currentIndex() == 0


def test_structure_tab_graph_fallback_auto_switches_to_grid(
    tmp_path: Path, monkeypatch
) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    # We don't need seed data here — we're monkeypatching the snapshot anyway,
    # but list_clips_with_tags still runs on tab.refresh() so struct_* tables
    # must exist (they do, courtesy of _build_struct_db).
    svc = BrainService(session_factory=Session)

    fake_count = 2500
    fake_nodes = [
        {
            "scene_id": i,
            "role": None,
            "mood_refined": None,
            "style_bucket_id": None,
            "style_bucket_name": None,
        }
        for i in range(fake_count)
    ]
    snapshot = {"nodes": fake_nodes, "edges": [], "scene_count": fake_count}

    tab = StructureTab(brain_service=svc)
    # Patch after construction — initial refresh uses the real DB.
    monkeypatch.setattr(svc, "graph_nodes_and_edges", lambda: snapshot)

    tab.set_view_mode("Graph")

    # Mode must have flipped back to Grid.
    assert tab._stack.currentIndex() == 0
    assert tab.current_view_mode() == "Grid"
    # Banner state: in headless mode QWidget.isVisible() returns False for
    # unshown parents, so check the explicit "hidden" flag instead.
    assert tab._fallback_banner.isHidden() is False
    assert "Too many scenes" in tab._fallback_banner.text()
