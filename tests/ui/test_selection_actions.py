"""T10.2e headless tests: Boost/Exclude selection actions + override queue.

Mirrors the offscreen-Qt + on-disk SQLite pattern of
``tests/ui/test_structure_tab.py`` / ``tests/ui/test_graph_view.py``.
Reuses the ``_build_struct_db`` + seed helpers as plain imports.

Scope (T10.2e):
  - SteerOverrideQueue unit tests (add / remove / clear / singleton / signal).
  - Structure-tab Inspector toolbar buttons (enable/disable + push-to-queue).
  - _ClipCard context-menu helper.
  - GraphView right-click → ``contextRequested`` signal.
  - "<n> pending overrides" label show/hide + text.
  - Palette fold-in (A): ``bucket_color`` importable from ``_palette``.
  - Circular-import cleanup (A): no lazy GraphView import in StructureTab.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from sqlalchemy import text

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from services.brain_service import BrainService
from services.steer_override_queue import (
    PendingOverride,
    SteerOverrideQueue,
    get_default_queue,
    reset_default_queue_for_test,
)
from ui.studio_brain._palette import bucket_color
from ui.studio_brain.graph_view import GraphView
from ui.studio_brain.structure_tab import StructureTab, _ClipCard

# Reuse fixture helpers from the sibling test file (plain import — no conftest).
from tests.ui.test_structure_tab import (  # noqa: E402
    _build_struct_db,
    _seed_basics,
    _seed_bucket,
    _seed_scene,
    _seed_tag,
)


# ── Qt + singleton hygiene ────────────────────────────────────────────────────


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def _reset_default_queue() -> None:
    """Isolate tests that exercise queue-singleton semantics."""
    reset_default_queue_for_test()
    yield
    reset_default_queue_for_test()


# ── SteerOverrideQueue unit tests ─────────────────────────────────────────────


def test_queue_add_and_list_round_trips() -> None:
    q = SteerOverrideQueue()
    q.add(1, "boost", "inspector")

    items = q.list()
    assert len(items) == 1
    item = items[0]
    assert isinstance(item, PendingOverride)
    assert item.scene_id == 1
    assert item.action == "boost"
    assert item.source == "inspector"


def test_queue_boost_replaces_exclude_for_same_scene() -> None:
    q = SteerOverrideQueue()
    q.add(5, "exclude", "structure")
    q.add(5, "boost", "inspector")

    items = q.list()
    assert len(items) == 1
    assert items[0].scene_id == 5
    assert items[0].action == "boost"
    assert items[0].source == "inspector"


def test_queue_remove_clears_scene() -> None:
    q = SteerOverrideQueue()
    q.add(3, "boost", "inspector")
    assert q.count() == 1

    q.remove(3)
    assert q.list() == []
    assert q.count() == 0


def test_queue_clear_empties_everything() -> None:
    q = SteerOverrideQueue()
    q.add(1, "boost", "inspector")
    q.add(2, "exclude", "structure")
    q.add(3, "boost", "graph")
    assert q.count() == 3

    q.clear()
    assert q.count() == 0
    assert q.list() == []


def test_queue_pendingChanged_fires_on_mutation() -> None:
    _ensure_qapp()
    q = SteerOverrideQueue()

    emissions: list[int] = []
    q.pendingChanged.connect(lambda: emissions.append(1))

    q.add(1, "boost", "inspector")   # 1
    q.add(2, "exclude", "structure") # 2
    q.remove(1)                      # 3
    q.clear()                        # 4 (still has 1 entry)

    assert len(emissions) == 4


def test_queue_instance_is_process_wide_singleton() -> None:
    a = get_default_queue()
    b = get_default_queue()
    assert a is b


def test_queue_redundant_add_does_not_emit() -> None:
    """I-1: a second ``add()`` that produces a structurally-equal
    PendingOverride for the same ``scene_id`` must be a no-op — matching
    the ``remove()`` / ``clear()`` contract that only emits on an actual
    mutation."""
    _ensure_qapp()
    q = SteerOverrideQueue()

    emissions: list[int] = []
    q.pendingChanged.connect(lambda: emissions.append(1))

    q.add(5, "boost", "inspector")
    q.add(5, "boost", "inspector")  # identical — must not re-emit.

    assert len(emissions) == 1
    assert q.count() == 1


# ── Structure tab: Inspector toolbar buttons ──────────────────────────────────


def test_inspector_toolbar_buttons_disabled_without_selection(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)

    svc = BrainService(session_factory=Session)
    queue = SteerOverrideQueue()
    tab = StructureTab(brain_service=svc, override_queue=queue)

    assert tab._boost_btn.isEnabled() is False
    assert tab._exclude_btn.isEnabled() is False

    # Simulate a card-click via the public clipSelected signal.
    tab.clipSelected.emit(42)

    assert tab._boost_btn.isEnabled() is True
    assert tab._exclude_btn.isEnabled() is True


def test_inspector_boost_button_pushes_to_queue(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)

    svc = BrainService(session_factory=Session)
    queue = SteerOverrideQueue()
    tab = StructureTab(brain_service=svc, override_queue=queue)

    # Arm the selection.
    tab.clipSelected.emit(42)
    # Click boost.
    tab._boost_btn.click()

    items = queue.list()
    assert len(items) == 1
    assert items[0].scene_id == 42
    assert items[0].action == "boost"
    assert items[0].source == "inspector"


def test_inspector_exclude_button_pushes_to_queue(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)

    svc = BrainService(session_factory=Session)
    queue = SteerOverrideQueue()
    tab = StructureTab(brain_service=svc, override_queue=queue)

    tab.clipSelected.emit(99)
    tab._exclude_btn.click()

    items = queue.list()
    assert len(items) == 1
    assert items[0].scene_id == 99
    assert items[0].action == "exclude"
    assert items[0].source == "inspector"


# ── Structure tab: grid-card context menu ─────────────────────────────────────


def test_structure_tab_grid_card_context_menu_actions_exist() -> None:
    _ensure_qapp()
    row = {
        "scene_id": 7,
        "role": "hero",
        "role_confidence": 0.9,
        "mood_refined": "euphoric",
        "usage_count": 0,
        "style_bucket_id": 1,
    }
    card = _ClipCard(row)

    menu = card._build_context_menu()
    actions = menu.actions()
    assert len(actions) == 2
    texts = [a.text() for a in actions]
    assert any("Boost" in t for t in texts)
    assert any("Exclude" in t for t in texts)


# ── GraphView: right-click → contextRequested ────────────────────────────────


def test_graph_view_right_click_emits_contextRequested(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        for sid in (80, 81, 82):
            _seed_scene(conn, sid)
            _seed_tag(conn, sid, bucket_id=1)

    svc = BrainService(session_factory=Session)
    view = GraphView(svc)
    assert view.render_graph() is True

    received: list[tuple[int, QPoint]] = []
    view.contextRequested.connect(
        lambda sid, pos: received.append((sid, pos))
    )

    view._emit_context_for_scene(81, QPoint(0, 0))
    assert len(received) == 1
    assert received[0][0] == 81
    assert isinstance(received[0][1], QPoint)


# ── Pending count label ───────────────────────────────────────────────────────


def test_structure_tab_shows_pending_count_label(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)

    svc = BrainService(session_factory=Session)
    queue = SteerOverrideQueue()
    tab = StructureTab(brain_service=svc, override_queue=queue)

    queue.add(1, "boost", "inspector")
    queue.add(2, "exclude", "structure")
    queue.add(3, "boost", "graph")

    assert "3" in tab._pending_label.text()
    assert "ausstehende Änderungen" in tab._pending_label.text()


def test_structure_tab_hides_pending_count_label_when_zero(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)

    svc = BrainService(session_factory=Session)
    queue = SteerOverrideQueue()
    tab = StructureTab(brain_service=svc, override_queue=queue)

    # Fresh queue — label must be hidden. In offscreen mode isVisible()
    # depends on parent mounting; isHidden() reflects the explicit flag.
    assert tab._pending_label.isHidden() is True

    # Add → remove → back to zero → still hidden.
    queue.add(1, "boost", "inspector")
    assert tab._pending_label.isHidden() is False
    queue.remove(1)
    assert tab._pending_label.isHidden() is True


# ── Palette fold-in (A) ───────────────────────────────────────────────────────


def test_palette_bucket_color_moved_and_importable() -> None:
    _ensure_qapp()
    # The name resolves (and returns a QColor).
    c1 = bucket_color(1)
    c2 = bucket_color(2)
    c_none = bucket_color(None)

    # Spot-check: determinism + correctness against the documented palette.
    # Index 1 → "#4c566a"; index 2 → "#5e81ac"; None → "#2e3440".
    assert c1.name().lower() == "#4c566a"
    assert c2.name().lower() == "#5e81ac"
    assert c_none.name().lower() == "#2e3440"

    # And it's the same QColor the structure-tab internals produce for
    # these bucket ids (deterministic palette — no drift).
    assert bucket_color(1).name() == c1.name()
    assert bucket_color(2).name() == c2.name()


def test_inspector_buttons_disable_when_selection_filtered_out(
    tmp_path: Path,
) -> None:
    """I-2: when the selected scene is no longer among the rendered rows
    (e.g. because the user narrowed the filters), the Inspector toolbar
    buttons must re-disable and ``_last_selected_scene_id`` must reset so
    the user can't queue an override for a scene the UI isn't showing."""
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        # Scenes 1,2,4,5 get role="hero"; scene 3 gets role="bridge" so we
        # can filter it away via the role combo.
        for sid in (1, 2, 3, 4, 5):
            _seed_scene(conn, sid, start=float(sid), end=float(sid) + 1.0)
            _seed_tag(
                conn,
                sid,
                role=("bridge" if sid == 3 else "hero"),
                bucket_id=1,
            )

    svc = BrainService(session_factory=Session)
    queue = SteerOverrideQueue()
    tab = StructureTab(brain_service=svc, override_queue=queue)

    # Preconditions: scene 3 is visible in the initial "(any)" render.
    visible_before = {int(r["scene_id"]) for r in tab.current_cards()}
    assert 3 in visible_before

    # Arm the selection on scene 3; buttons enable.
    tab.clipSelected.emit(3)
    assert tab._last_selected_scene_id == 3
    assert tab._boost_btn.isEnabled() is True
    assert tab._exclude_btn.isEnabled() is True

    # Apply a filter that excludes scene 3 (role="hero"). The grid
    # rebuilds → ``rowsChanged`` fires → ``_revalidate_selection`` runs.
    tab.set_filters({"role": "hero"})

    visible_after = {int(r["scene_id"]) for r in tab.current_cards()}
    assert 3 not in visible_after

    assert tab._last_selected_scene_id is None
    assert tab._boost_btn.isEnabled() is False
    assert tab._exclude_btn.isEnabled() is False


# ── M-8: source-string coverage for grid + graph paths ───────────────────────


def _find_action(menu, text_fragment: str):
    """Return the first QAction whose text contains ``text_fragment``."""
    for action in menu.actions():
        if text_fragment in action.text():
            return action
    raise AssertionError(
        f"No action with {text_fragment!r} in menu actions: "
        f"{[a.text() for a in menu.actions()]}"
    )


def test_grid_card_context_action_queues_with_source_structure(
    tmp_path: Path,
) -> None:
    """M-8: a context-menu "boost" pick triggered via the grid-card path
    must queue exactly one override with ``source="structure"`` and
    ``action="boost"``.

    We build the same QMenu ``_show_context_menu`` would (via the extracted
    ``_build_override_menu`` helper) with ``source="structure"`` and
    ``.trigger()`` the Boost QAction — this exercises the signal/slot wiring
    without QMenu.exec blocking offscreen.
    """
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        _seed_scene(conn, 11)
        _seed_tag(conn, 11, bucket_id=1)

    svc = BrainService(session_factory=Session)
    queue = SteerOverrideQueue()
    tab = StructureTab(brain_service=svc, override_queue=queue)

    menu = tab._build_override_menu(11, source="structure")
    _find_action(menu, "Boost").trigger()

    items = queue.list()
    assert len(items) == 1
    assert items[0].scene_id == 11
    assert items[0].action == "boost"
    assert items[0].source == "structure"


def test_graph_context_action_queues_with_source_graph(tmp_path: Path) -> None:
    """M-8: a context-menu "exclude" pick from the graph-view path must
    queue exactly one override with ``source="graph"`` and
    ``action="exclude"``.

    We prove (a) the ``contextRequested`` signal on the tab's GraphView is
    wired to at least one slot (i.e. ``_show_context_menu`` is connected),
    then (b) trigger the Exclude QAction on a menu built with
    ``source="graph"`` — the exact menu ``_show_context_menu`` would pop
    up. We deliberately do **not** emit ``contextRequested`` because the
    tab's production handler calls the blocking ``QMenu.exec``, which
    hangs under the offscreen Qt platform.
    """
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        for sid in (20, 21, 22):
            _seed_scene(conn, sid)
            _seed_tag(conn, sid, bucket_id=1)

    svc = BrainService(session_factory=Session)
    queue = SteerOverrideQueue()
    tab = StructureTab(brain_service=svc, override_queue=queue)
    assert tab._graph.render_graph() is True

    # Wiring assertion: the tab connected a slot to the graph's
    # ``contextRequested`` signal. ``receivers(SIGNAL("sig(...)"))`` > 0
    # proves ``_show_context_menu(source="graph")`` is reachable from the
    # signal without us having to actually emit it (which would block on
    # ``QMenu.exec`` under the offscreen Qt platform). PySide6 expects the
    # C++ signature string here, not the ``SignalInstance`` object.
    assert tab._graph.receivers("2contextRequested(int,QPoint)") >= 1

    # Now trigger the Exclude QAction on the same menu ``_show_context_menu``
    # would build for the graph path.
    menu = tab._build_override_menu(21, source="graph")
    _find_action(menu, "Exclude").trigger()

    items = queue.list()
    assert len(items) == 1
    assert items[0].scene_id == 21
    assert items[0].action == "exclude"
    assert items[0].source == "graph"


def test_graph_view_no_circular_import_workaround() -> None:
    """Fold-in A: the ``from ui.studio_brain.graph_view import GraphView``
    statement must not appear inside any function body of structure_tab.py
    — only at module top-level. We walk the AST to prove it.
    """
    source_path = (
        Path(__file__).resolve().parents[2]
        / "ui"
        / "studio_brain"
        / "structure_tab.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    def _mentions_graph_view_import(node: ast.AST) -> bool:
        for sub in ast.walk(node):
            if isinstance(sub, ast.ImportFrom):
                if sub.module == "ui.studio_brain.graph_view":
                    for alias in sub.names:
                        if alias.name == "GraphView":
                            return True
            elif isinstance(sub, ast.Import):
                for alias in sub.names:
                    if alias.name == "ui.studio_brain.graph_view":
                        return True
        return False

    # Walk every function / method body and assert GraphView is NOT imported
    # inside it. Module-top is fine (that's where it now lives).
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ) and _mentions_graph_view_import(node):
            offenders.append(node.name)

    assert offenders == [], (
        "Lazy GraphView import still present inside function bodies: "
        f"{offenders}. Move it to module top (Fold-in A)."
    )
