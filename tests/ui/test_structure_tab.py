"""T10.2a headless tests: StructureTab grid + filters + BrainService methods.

Offscreen Qt + in-memory SQLite, mirroring the pattern of
tests/ui/test_studio_brain_window.py and tests/ui/test_feedback_shortcuts.py.

All tests use the `_build_struct_db` helper which bootstraps
audio_tracks / video_clips / scenes then runs Alembic to head so the
struct_* and mem_* tables all exist.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from PySide6.QtWidgets import QApplication

from services.brain_service import BrainService
from services.enrichment import ENRICHER_VERSION
from ui.studio_brain.structure_tab import StructureTab, _ClipCard
from ui.studio_brain_window import StudioBrainWindow


# ── Qt + singleton hygiene ────────────────────────────────────────────────────


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
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


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _build_struct_db(tmp_path: Path) -> tuple[Any, Any]:
    """SQLite at tmp_path, migrated to head; struct_* tables exist."""
    from alembic import command
    from alembic.config import Config

    db_path = tmp_path / "struct.db"

    bootstrap_engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    with bootstrap_engine.begin() as conn:
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
                energy REAL,
                FOREIGN KEY (video_clip_id) REFERENCES video_clips(id)
            )
        """))
    bootstrap_engine.dispose()

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    return engine, sessionmaker(bind=engine)


def _seed_video_clip(conn, clip_id: int = 1) -> None:
    conn.execute(
        text(
            "INSERT INTO video_clips (id, file_path, original_filename, sha256, status, created_at) "
            "VALUES (:cid, '/v.mp4', 'v.mp4', 'v-sha', 'ready', datetime('now'))"
        ),
        {"cid": clip_id},
    )


def _seed_audio_track(conn, track_id: int = 1) -> None:
    conn.execute(
        text(
            "INSERT INTO audio_tracks (id, file_path, original_filename, sha256, status, created_at) "
            "VALUES (:aid, '/a.mp3', 'a.mp3', 'a-sha', 'ready', datetime('now'))"
        ),
        {"aid": track_id},
    )


def _seed_scene(conn, scene_id: int, clip_id: int = 1, start: float = 0.0, end: float = 5.0) -> None:
    conn.execute(
        text(
            "INSERT INTO scenes (id, video_clip_id, start_time, end_time) "
            "VALUES (:sid, :cid, :s, :e)"
        ),
        {"sid": scene_id, "cid": clip_id, "s": start, "e": end},
    )


def _seed_bucket(
    conn,
    bucket_id: int,
    name: str,
    active: bool = True,
    member_count: int = 1,
) -> None:
    conn.execute(
        text(
            "INSERT INTO struct_style_bucket "
            "(id, name, description, centroid_embedding, member_count, created_at, "
            " enricher_version, active) VALUES "
            "(:id, :name, :desc, :emb, :mc, :ts, :ver, :active)"
        ),
        {
            "id": bucket_id,
            "name": name,
            "desc": f"bucket {name}",
            "emb": b"\x00" * 8,
            "mc": member_count,
            "ts": datetime.now(timezone.utc),
            "ver": ENRICHER_VERSION,
            "active": 1 if active else 0,
        },
    )


def _seed_tag(
    conn,
    scene_id: int,
    role: str = "hero",
    role_conf: float = 0.9,
    mood: str = "euphoric",
    mood_conf: float = 0.8,
    bucket_id: int = 1,
    distance: float = 0.12,
) -> None:
    conn.execute(
        text(
            "INSERT INTO struct_clip_tags "
            "(scene_id, role, role_confidence, mood_refined, mood_confidence, "
            " style_bucket_id, style_distance, enriched_at, enricher_version) "
            "VALUES (:sid, :role, :rc, :mood, :mc, :bid, :d, :ts, :ver)"
        ),
        {
            "sid": scene_id,
            "role": role,
            "rc": role_conf,
            "mood": mood,
            "mc": mood_conf,
            "bid": bucket_id,
            "d": distance,
            "ts": datetime.now(timezone.utc),
            "ver": ENRICHER_VERSION,
        },
    )


def _seed_run(conn, run_id: int = 1) -> None:
    conn.execute(
        text(
            "INSERT INTO mem_pacing_run (id, audio_track_id, started_at, is_dj_mix, "
            "total_duration_sec, total_cuts, agent_version, weights_profile) "
            "VALUES (:id, 1, :ts, 0, 120.0, 0, 'test', 'default')"
        ),
        {"id": run_id, "ts": datetime.now(timezone.utc)},
    )


def _seed_decision(
    conn, run_id: int, scene_id: int, sequence_idx: int = 0
) -> None:
    conn.execute(
        text("""
            INSERT INTO mem_decision
            (run_id, sequence_idx, at_timestamp_sec, at_section_type, at_bpm,
             at_genre, at_enricher_version, scene_id, clip_role, clip_mood_refined,
             clip_style_bucket_id, agent_score, agent_rationale, user_verdict)
            VALUES (:rid, :seq, 60.0, 'drop', 140.0, 'psytrance', :ver, :sid,
                    'hero', 'euphoric', 1, 0.7, '{}', NULL)
        """),
        {
            "rid": run_id,
            "seq": sequence_idx,
            "sid": scene_id,
            "ver": ENRICHER_VERSION,
        },
    )


def _seed_basics(engine: Any) -> None:
    """Shared prelude: video clip + audio track + pacing run."""
    with engine.begin() as conn:
        _seed_video_clip(conn)
        _seed_audio_track(conn)
        _seed_run(conn)


# ── BrainService tests ────────────────────────────────────────────────────────


def test_list_active_style_buckets_excludes_inactive(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm", active=True)
        _seed_bucket(conn, 2, "Cool", active=True)
        _seed_bucket(conn, 3, "Legacy", active=False)

    svc = BrainService(session_factory=Session)
    buckets = svc.list_active_style_buckets()
    names = sorted(b["name"] for b in buckets)
    assert names == ["Cool", "Warm"]
    assert len(buckets) == 2


def test_list_clips_with_tags_returns_joined_rows(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        for sid in (10, 11, 12):
            _seed_scene(conn, sid)
            _seed_tag(conn, sid, bucket_id=1)

    svc = BrainService(session_factory=Session)
    rows = svc.list_clips_with_tags()
    assert len(rows) == 3
    assert all(r["style_bucket_name"] == "Warm" for r in rows)
    assert {r["scene_id"] for r in rows} == {10, 11, 12}


def test_list_clips_with_tags_filters_by_role(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        _seed_scene(conn, 20)
        _seed_scene(conn, 21)
        _seed_scene(conn, 22)
        _seed_tag(conn, 20, role="hero", bucket_id=1)
        _seed_tag(conn, 21, role="hero", bucket_id=1)
        _seed_tag(conn, 22, role="filler", bucket_id=1)

    svc = BrainService(session_factory=Session)
    rows = svc.list_clips_with_tags(role="hero")
    assert len(rows) == 2
    assert all(r["role"] == "hero" for r in rows)


def test_list_clips_with_tags_filters_by_min_confidence(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        _seed_scene(conn, 30)
        _seed_scene(conn, 31)
        _seed_scene(conn, 32)
        _seed_tag(conn, 30, role_conf=0.3, bucket_id=1)
        _seed_tag(conn, 31, role_conf=0.7, bucket_id=1)
        _seed_tag(conn, 32, role_conf=0.9, bucket_id=1)

    svc = BrainService(session_factory=Session)
    rows = svc.list_clips_with_tags(min_role_confidence=0.6)
    assert len(rows) == 2
    assert all(r["role_confidence"] >= 0.6 for r in rows)


def test_list_clips_with_tags_filters_by_style_bucket(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        _seed_bucket(conn, 2, "Cool")
        _seed_scene(conn, 40)
        _seed_scene(conn, 41)
        _seed_scene(conn, 42)
        _seed_tag(conn, 40, bucket_id=1)
        _seed_tag(conn, 41, bucket_id=1)
        _seed_tag(conn, 42, bucket_id=2)

    svc = BrainService(session_factory=Session)
    rows = svc.list_clips_with_tags(style_bucket_id=2)
    assert len(rows) == 1
    assert rows[0]["scene_id"] == 42
    assert rows[0]["style_bucket_name"] == "Cool"


def test_list_clips_with_tags_usage_count_from_mem_decision(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        _seed_scene(conn, 50)  # A — referenced 3x
        _seed_scene(conn, 51)  # B — referenced 0x
        _seed_tag(conn, 50, bucket_id=1)
        _seed_tag(conn, 51, bucket_id=1)
        _seed_decision(conn, run_id=1, scene_id=50, sequence_idx=0)
        _seed_decision(conn, run_id=1, scene_id=50, sequence_idx=1)
        _seed_decision(conn, run_id=1, scene_id=50, sequence_idx=2)

    svc = BrainService(session_factory=Session)
    rows = svc.list_clips_with_tags()
    by_scene = {r["scene_id"]: r for r in rows}
    assert by_scene[50]["usage_count"] == 3
    assert by_scene[51]["usage_count"] == 0

    svc2 = BrainService(session_factory=Session)  # fresh cache
    filtered = svc2.list_clips_with_tags(min_usage_count=1)
    assert len(filtered) == 1
    assert filtered[0]["scene_id"] == 50


# ── StructureTab tests ────────────────────────────────────────────────────────


def _seed_five_scenes(engine: Any) -> None:
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        _seed_bucket(conn, 2, "Cool")
        # 3 hero (bucket 1) + 2 filler (bucket 2)
        _seed_scene(conn, 100)
        _seed_scene(conn, 101)
        _seed_scene(conn, 102)
        _seed_scene(conn, 103)
        _seed_scene(conn, 104)
        _seed_tag(conn, 100, role="hero", bucket_id=1)
        _seed_tag(conn, 101, role="hero", bucket_id=1)
        _seed_tag(conn, 102, role="hero", bucket_id=1)
        _seed_tag(conn, 103, role="filler", bucket_id=2)
        _seed_tag(conn, 104, role="filler", bucket_id=2)


def test_structure_tab_renders_one_card_per_scene(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    _seed_five_scenes(engine)

    svc = BrainService(session_factory=Session)
    tab = StructureTab(brain_service=svc)
    tab.refresh()

    cards = tab.current_cards()
    assert len(cards) == 5
    assert {c["scene_id"] for c in cards} == {100, 101, 102, 103, 104}
    # Issue #12: data rows alone don't prove widgets were built — assert the
    # QWidget tree actually materialised one _ClipCard per row.
    assert len(tab.findChildren(_ClipCard)) == 5


def test_structure_tab_filter_change_refreshes_grid(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    _seed_five_scenes(engine)

    svc = BrainService(session_factory=Session)
    tab = StructureTab(brain_service=svc)

    # Baseline: all 5 visible.
    assert len(tab.current_cards()) == 5

    tab.set_filters({"role": "hero"})
    cards = tab.current_cards()
    assert len(cards) == 3
    assert all(c["role"] == "hero" for c in cards)

    # Relax: back to all.
    tab.set_filters(
        {
            "role": None,
            "mood": None,
            "style_bucket_id": None,
            "min_role_confidence": 0.0,
            "min_usage_count": 0,
        }
    )
    assert len(tab.current_cards()) == 5


def test_structure_tab_emits_clipSelected_on_card_click(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        _seed_scene(conn, 77)
        _seed_tag(conn, 77, bucket_id=1)

    svc = BrainService(session_factory=Session)
    tab = StructureTab(brain_service=svc)

    received: list[int] = []
    tab.clipSelected.connect(received.append)

    # Find the card we just rendered and simulate its internal "clicked" signal.
    cards = tab.findChildren(_ClipCard)
    assert len(cards) == 1
    cards[0].clicked.emit(cards[0].scene_id)

    assert received == [77]


def test_studio_brain_window_index_0_is_structure_tab(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)

    svc = BrainService(session_factory=Session)
    win = StudioBrainWindow.reset_for_test(brain_service=svc)
    try:
        # B-184: 6 Tabs seit Cycle 11 / D-023 (Pacing-Explorer + Graph-Cockpit).
        assert win.count_tabs() == 6
        assert type(win._tabs.widget(0)).__name__ == "StructureTab"
        labels = [win._tabs.tabText(i) for i in range(win.count_tabs())]
        assert labels == [
            "Struktur",
            "Gedächtnis",
            "Audit",
            "Steer",
            "Pacing-Explorer",
            "Graph-Cockpit",
        ]
    finally:
        win.close()


# ── Review-dispatch tests (Fixes #1-#3 + Issues #12-#13) ──────────────────────


def test_list_distinct_roles(tmp_path: Path) -> None:
    """Issue #13: 3 scenes, 2 distinct roles → sorted list of 2."""
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        _seed_scene(conn, 200)
        _seed_scene(conn, 201)
        _seed_scene(conn, 202)
        _seed_tag(conn, 200, role="hero", bucket_id=1)
        _seed_tag(conn, 201, role="filler", bucket_id=1)
        _seed_tag(conn, 202, role="hero", bucket_id=1)

    svc = BrainService(session_factory=Session)
    roles = svc.list_distinct_roles()
    assert roles == ["filler", "hero"]


def test_list_distinct_moods(tmp_path: Path) -> None:
    """Issue #13: 3 scenes, 2 distinct moods → sorted list of 2."""
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        _seed_scene(conn, 210)
        _seed_scene(conn, 211)
        _seed_scene(conn, 212)
        _seed_tag(conn, 210, mood="euphoric", bucket_id=1)
        _seed_tag(conn, 211, mood="brooding", bucket_id=1)
        _seed_tag(conn, 212, mood="euphoric", bucket_id=1)

    svc = BrainService(session_factory=Session)
    moods = svc.list_distinct_moods()
    assert moods == ["brooding", "euphoric"]


def test_brain_service_invalidate_clears_cache(tmp_path: Path) -> None:
    """Fix #1: invalidate() drops every wrapped lru_cache on the instance."""
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        _seed_scene(conn, 300)
        _seed_tag(conn, 300, bucket_id=1)

    svc = BrainService(session_factory=Session)

    # First call populates the cache.
    svc.list_clips_with_tags()
    wrapper = svc._list_clips_with_tags_cached
    info_before = wrapper.cache_info()
    hits_before = info_before.hits
    # Second call with identical args must hit the cache.
    svc.list_clips_with_tags()
    info_after = wrapper.cache_info()
    assert info_after.hits > hits_before

    # Also seed one of the no-arg caches so we can observe currsize.
    svc.list_distinct_roles()
    assert svc.list_distinct_roles.cache_info().currsize == 1

    # Invalidate drops every cache.
    svc.invalidate()
    assert svc.list_distinct_roles.cache_info().currsize == 0
    assert wrapper.cache_info().currsize == 0


def test_safe_call_reraises_non_operationalerror(tmp_path: Path) -> None:
    """Fix #2: BrainService listing methods that raise non-OperationalError
    propagate out of tab construction instead of being silently swallowed.
    """
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)

    svc = BrainService(session_factory=Session)

    def boom() -> list:
        raise RuntimeError("schema drift in list_distinct_roles")

    svc.list_distinct_roles = boom  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="schema drift"):
        StructureTab(brain_service=svc)


def test_set_filters_is_partial_patch(tmp_path: Path) -> None:
    """Fix #3: set_filters overlays on the current bar state instead of
    resetting unspecified keys to defaults.
    """
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    _seed_five_scenes(engine)

    svc = BrainService(session_factory=Session)
    tab = StructureTab(brain_service=svc)
    bar = tab._filter_bar

    # Patch role only — mood stays None, spins stay at defaults.
    tab.set_filters({"role": "hero"})
    cur = bar.current_filters()
    assert cur["role"] == "hero"
    assert cur["mood"] is None
    assert cur["style_bucket_id"] is None
    assert cur["min_role_confidence"] == 0.0
    assert cur["min_usage_count"] == 0

    # Now patch mood — role must survive.
    tab.set_filters({"mood": "euphoric"})
    cur = bar.current_filters()
    assert cur["role"] == "hero"
    assert cur["mood"] == "euphoric"
