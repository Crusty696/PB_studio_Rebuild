"""T10.2c headless tests: StatsPanel + BrainService.structure_stats.

Offscreen Qt + on-disk SQLite via tmp_path, mirroring the pattern used by
tests/ui/test_structure_tab.py and tests/ui/test_inspector_panel.py. The
fixture helpers are imported as a plain module import from
test_structure_tab (no conftest indirection) so we get tight coupling
without fighting fixture scope.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from PySide6.QtWidgets import QApplication

from services.brain import BrainService
from services.brain.legacy_sqlite import _load_expected_moods
from ui.studio_brain.stats_panel import StatsPanel
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


@pytest.fixture(autouse=True)
def _clear_expected_moods_cache() -> None:
    """Force every test to re-parse mood_anchors_v1.yaml.

    The module-level lru_cache on ``_load_expected_moods`` would otherwise
    leak between tests, hiding any future regression where the helper's
    result no longer depends on the YAML file.
    """
    _load_expected_moods.cache_clear()
    yield
    _load_expected_moods.cache_clear()


# ── Local helpers ─────────────────────────────────────────────────────────────


def _build_bare_scenes_db(tmp_path: Path) -> tuple[Any, Any]:
    """Minimal SQLite with ONLY audio_tracks/video_clips/scenes — no struct_*
    tables. Used to exercise the OperationalError path of StatsPanel."""
    db_path = tmp_path / "bare.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE audio_tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at DATETIME NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE video_clips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at DATETIME NOT NULL
            )
        """))
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


# ── BrainService.structure_stats tests ────────────────────────────────────────


def test_structure_stats_empty_db_returns_zero_counts(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)

    svc = BrainService(session_factory=Session)
    stats = svc.structure_stats()

    assert stats["total_scenes"] == 0
    assert stats["enriched_scenes"] == 0
    assert stats["coverage_fraction"] == 0.0
    assert stats["role_counts"] == []
    assert stats["mood_counts"] == []
    assert stats["active_style_buckets"] == 0

    # All expected anchor labels should appear in missing_moods when nothing
    # has been tagged yet.
    expected = _load_expected_moods()
    assert expected, "expected moods list should be non-empty"
    assert stats["missing_moods"] == sorted(expected)


def test_structure_stats_counts_from_tagged_rows(tmp_path: Path) -> None:
    """10 scenes, 7 tagged (hero×4, filler×2, transition×1 ;
    euphoric×5, melancholic×2)."""
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        # 10 total scenes.
        for sid in range(1000, 1010):
            _seed_scene(conn, sid)
        # 7 tagged: 4 hero+euphoric, 2 filler+euphoric, 1 transition+melancholic.
        # That gives euphoric=6 / melancholic=1 — but the task states
        # euphoric 5 / melancholic 2. Arrange tags accordingly:
        #   hero × 4   — 3 euphoric + 1 melancholic
        #   filler × 2 — 2 euphoric
        #   transition × 1 — 1 melancholic
        tag_plan = [
            (1000, "hero", "euphoric"),
            (1001, "hero", "euphoric"),
            (1002, "hero", "euphoric"),
            (1003, "hero", "melancholic"),
            (1004, "filler", "euphoric"),
            (1005, "filler", "euphoric"),
            (1006, "transition", "melancholic"),
        ]
        for sid, role, mood in tag_plan:
            _seed_tag(conn, sid, role=role, mood=mood, bucket_id=1)

    svc = BrainService(session_factory=Session)
    stats = svc.structure_stats()

    assert stats["total_scenes"] == 10
    assert stats["enriched_scenes"] == 7
    assert stats["role_counts"] == [
        ("hero", 4),
        ("filler", 2),
        ("transition", 1),
    ]
    # Mood sanity: euphoric=5, melancholic=2 → sorted DESC by count.
    assert stats["mood_counts"] == [
        ("euphoric", 5),
        ("melancholic", 2),
    ]


def test_structure_stats_coverage_fraction(tmp_path: Path) -> None:
    """10 total scenes, 7 enriched → coverage_fraction == 0.7."""
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        for sid in range(2000, 2010):
            _seed_scene(conn, sid)
        for sid in range(2000, 2007):
            _seed_tag(conn, sid, bucket_id=1)

    svc = BrainService(session_factory=Session)
    stats = svc.structure_stats()
    assert stats["total_scenes"] == 10
    assert stats["enriched_scenes"] == 7
    assert stats["coverage_fraction"] == pytest.approx(0.7)


def test_structure_stats_active_bucket_count(tmp_path: Path) -> None:
    """2 active + 1 inactive bucket → active_style_buckets == 2."""
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm", active=True)
        _seed_bucket(conn, 2, "Cool", active=True)
        _seed_bucket(conn, 3, "Legacy", active=False)

    svc = BrainService(session_factory=Session)
    stats = svc.structure_stats()
    assert stats["active_style_buckets"] == 2


def test_structure_stats_missing_moods_from_yaml_anchors(tmp_path: Path) -> None:
    """Missing moods reflect mood_anchors_v1.yaml minus moods present in
    struct_clip_tags. Using 'euphoric' removes it from the gap list."""
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)

    expected = _load_expected_moods()
    assert "euphoric" in expected, (
        "test fixture assumes 'euphoric' is an anchor label — check "
        "config/mood_anchors_v1.yaml"
    )

    # No moods used yet → every anchor label is a gap.
    svc_empty = BrainService(session_factory=Session)
    gaps_empty = svc_empty.structure_stats()["missing_moods"]
    assert set(gaps_empty) == set(expected)
    for label in expected:
        assert label in gaps_empty

    # Tag one scene with euphoric → euphoric drops from the gap list.
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        _seed_scene(conn, 3000)
        _seed_tag(conn, 3000, mood="euphoric", bucket_id=1)

    svc_partial = BrainService(session_factory=Session)
    gaps_partial = svc_partial.structure_stats()["missing_moods"]
    assert "euphoric" not in gaps_partial
    # Every other anchor label still counts as a gap.
    for label in expected:
        if label != "euphoric":
            assert label in gaps_partial


def test_load_expected_moods_from_yaml() -> None:
    """Shape check on the real config/mood_anchors_v1.yaml: non-empty
    list of strings."""
    labels = _load_expected_moods()
    assert isinstance(labels, list)
    assert len(labels) > 0
    assert all(isinstance(label, str) and label for label in labels)


# ── StatsPanel widget tests ───────────────────────────────────────────────────


def _collect_list_items(list_widget) -> list[str]:
    """Return the text of each row in a QListWidget."""
    return [list_widget.item(i).text() for i in range(list_widget.count())]


def test_stats_panel_renders_values(tmp_path: Path) -> None:
    """Construct a panel with a seeded DB (10 total, 7 enriched, 70% coverage,
    at least one role + one mood) and assert the visible labels contain the
    expected numeric strings."""
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        _seed_bucket(conn, 2, "Cool", active=False)
        for sid in range(4000, 4010):
            _seed_scene(conn, sid)
        # 7 tagged, all hero+euphoric, bucket 1.
        for sid in range(4000, 4007):
            _seed_tag(conn, sid, role="hero", mood="euphoric", bucket_id=1)

    svc = BrainService(session_factory=Session)
    panel = StatsPanel(svc)
    panel.refresh()

    coverage_text = panel._coverage_label.text()
    assert "7" in coverage_text
    assert "10" in coverage_text
    assert "70%" in coverage_text

    buckets_text = panel._buckets_label.text()
    assert "1" in buckets_text  # 1 active bucket (Warm)

    role_rows = _collect_list_items(panel._roles_list)
    assert any("hero" in r and "7" in r for r in role_rows)

    mood_rows = _collect_list_items(panel._moods_list)
    assert any("euphoric" in r and "7" in r for r in mood_rows)

    # Since only euphoric is used, other anchor labels show in coverage gaps.
    gaps_text = panel._gaps_label.text()
    expected = _load_expected_moods()
    missing_expected = [label for label in expected if label != "euphoric"]
    # At least one of the other anchors should appear in the displayed gaps.
    assert any(label in gaps_text for label in missing_expected)


def test_stats_panel_shows_graceful_message_on_operationalerror(
    tmp_path: Path,
) -> None:
    """DB with NO struct_* tables → panel must not crash and must show the
    'Stats unavailable' message."""
    _ensure_qapp()
    engine, Session = _build_bare_scenes_db(tmp_path)

    svc = BrainService(session_factory=Session)
    panel = StatsPanel(svc)  # __init__ calls refresh()
    # Force another explicit refresh — same graceful path.
    panel.refresh()

    assert panel._status_label.isHidden() is False
    assert "nicht verfügbar" in panel._status_label.text().lower()

    # The body widgets are hidden on the graceful path.
    assert panel._coverage_label.isHidden() is True
    assert panel._roles_list.isHidden() is True
    assert panel._moods_list.isHidden() is True


def test_stats_panel_refresh_propagates_non_operationalerror(
    tmp_path: Path,
) -> None:
    """Non-OperationalError exceptions must propagate, same narrow-catch
    rule the FilterBar and StructureTab follow."""
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)

    svc = BrainService(session_factory=Session)
    panel = StatsPanel(svc)

    def boom() -> dict:
        raise RuntimeError("boom")

    svc.structure_stats = boom  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="boom"):
        panel.refresh()


def test_structure_tab_refresh_also_refreshes_stats(tmp_path: Path) -> None:
    """StructureTab.refresh() must invoke StatsPanel.refresh exactly once
    per call, so library-level stats stay in sync when enrichment finishes
    in the background (even though filters alone don't move them)."""
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        _seed_scene(conn, 5000)
        _seed_tag(conn, 5000, bucket_id=1)

    svc = BrainService(session_factory=Session)
    tab = StructureTab(brain_service=svc)

    # Patch the *instance* method after construction so the initial refresh()
    # during __init__ doesn't count against us — we care about explicit
    # tab.refresh() calls.
    call_count = {"n": 0}
    original_refresh = tab._stats.refresh

    def spy() -> None:
        call_count["n"] += 1
        original_refresh()

    tab._stats.refresh = spy  # type: ignore[method-assign]

    tab.refresh()
    assert call_count["n"] == 1

    tab.refresh()
    assert call_count["n"] == 2
