"""T10.1 headless tests: StudioBrainWindow singleton + BrainService smoke.

These tests follow the offscreen Qt pattern from test_feedback_shortcuts.py —
no pytest-qt/qtbot, just plain QApplication + show + direct assertions.

The singleton state is reset between tests so that test ordering does not
leak instance identity.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import shiboken6
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from PySide6.QtWidgets import QApplication

from services.brain import BrainService
from ui.studio_brain_window import StudioBrainWindow


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    """Isolate tests that exercise singleton semantics."""
    StudioBrainWindow._instance = None
    yield
    inst = StudioBrainWindow._instance
    if inst is not None:
        try:
            inst.close()
            inst.deleteLater()
        except Exception:
            pass
    StudioBrainWindow._instance = None


def _build_scenes_sqlite(tmp_path: Path) -> tuple[Any, Any]:
    """Minimal in-memory SQLite with just the `scenes` table — enough for
    BrainService.list_scene_count()."""
    db_path = tmp_path / "brain.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE scenes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_clip_id INTEGER NOT NULL,
                start_time REAL NOT NULL,
                end_time REAL NOT NULL,
                label TEXT,
                energy REAL
            )
        """))
    return engine, sessionmaker(bind=engine)


def test_window_opens_offscreen() -> None:
    _ensure_qapp()
    w = StudioBrainWindow.instance()
    w.show()
    # B-184: 6 Tabs seit Cycle 11 / Pacing-v2 / D-023 (Pacing-Explorer + Graph-Cockpit).
    assert w.count_tabs() == 6
    assert w.windowTitle() == "Studio Brain"


def test_singleton_second_open_raises_existing() -> None:
    _ensure_qapp()
    w1 = StudioBrainWindow.instance()
    w2 = StudioBrainWindow.instance()
    assert w1 is w2


def test_tab_labels_are_six_german_sections() -> None:
    # B-184: Tabs seit Cycle 11 / D-023 (Pacing-Explorer + Graph-Cockpit ergänzt).
    _ensure_qapp()
    w = StudioBrainWindow.instance()
    labels = [w._tabs.tabText(i) for i in range(w.count_tabs())]
    assert labels == [
        "Struktur",
        "Gedächtnis",
        "Audit",
        "Steer",
        "Pacing-Explorer",
        "Graph-Cockpit",
    ]


def test_brain_service_list_scene_count_returns_int(tmp_path: Path) -> None:
    engine, Session = _build_scenes_sqlite(tmp_path)

    svc = BrainService(session_factory=Session)
    assert svc.list_scene_count() == 0

    with engine.begin() as conn:
        for i in range(3):
            conn.execute(
                text(
                    "INSERT INTO scenes (video_clip_id, start_time, end_time) "
                    "VALUES (1, :s, :e)"
                ),
                {"s": float(i), "e": float(i + 1)},
            )

    # New service instance so the lru_cache does not mask the new row count.
    svc2 = BrainService(session_factory=Session)
    assert svc2.list_scene_count() == 3
    assert isinstance(svc2.list_scene_count(), int)


def test_singleton_resurrects_after_cpp_deletion() -> None:
    """After the underlying C++ QMainWindow is deleted, `.instance()` must
    return a fresh, valid window — never a dangling Python reference.

    Regression guard for the `shiboken6.isValid` check in `instance()`.
    Without the check, the second `.instance()` call would return the
    same Python object whose C++ half is gone, and any attribute access
    would raise ``RuntimeError: Internal C++ object ... already deleted.``

    Note: we simulate the end state of `close() + deleteLater() + event
    loop reap` by calling `shiboken6.delete()` directly. Under the
    offscreen QPA, `deleteLater()` alone is not always reaped eagerly
    by `processEvents()`, which would make the test flaky. The failure
    mode we're guarding against (C++ object gone, Python reference
    stale) is identical regardless of which path reaped it.
    """
    app = _ensure_qapp()

    w1 = StudioBrainWindow.instance()
    assert shiboken6.isValid(w1)

    w1.close()
    # Force deterministic C++ deletion so the test exercises the
    # resurrection path on every platform/QPA.
    shiboken6.delete(w1)
    app.processEvents()

    assert not shiboken6.isValid(w1), (
        "expected the C++ QMainWindow to be gone after shiboken6.delete()"
    )

    w2 = StudioBrainWindow.instance()
    assert shiboken6.isValid(w2)
    assert w2 is not w1
    # B-184: 6 Tabs seit Cycle 11 / Pacing-v2 / D-023.
    assert w2.count_tabs() == 6
