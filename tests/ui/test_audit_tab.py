"""T11.2 headless tests: AuditTab (run selector + segment strip + cut table +
term contributions + alternatives + budget state) and the BrainService reads
backing it.

Follows the same offscreen-Qt + on-disk SQLite pattern as
tests/ui/test_memory_tab.py; the ``_build_struct_db`` helper from
``tests/ui/test_structure_tab.py`` is reused directly — it migrates the DB to
head, so mem_pacing_run / mem_decision / structure_segments all exist.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from sqlalchemy import text

from PySide6.QtWidgets import QApplication

from services.backup_service import BackupService
from services.brain_service import BrainService
from services.enrichment import ENRICHER_VERSION
from tests.ui.test_structure_tab import _build_struct_db
from ui.studio_brain.audit_tab import AuditTab
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


# ── Seed helpers ──────────────────────────────────────────────────────────────


def _seed_audio_track(
    conn, track_id: int = 1, file_path: str = "/mixes/set_01.mp3"
) -> None:
    conn.execute(
        text(
            "INSERT INTO audio_tracks (id, file_path, original_filename, "
            "sha256, status, created_at) "
            "VALUES (:id, :fp, :fn, 'a-sha-' || :id, 'ready', datetime('now'))"
        ),
        {"id": track_id, "fp": file_path, "fn": os.path.basename(file_path)},
    )


def _seed_video_clip(
    conn, clip_id: int = 1, file_path: str = "/videos/clip_01.mp4"
) -> None:
    conn.execute(
        text(
            "INSERT INTO video_clips (id, file_path, original_filename, "
            "sha256, status, created_at) "
            "VALUES (:id, :fp, :fn, 'v-sha-' || :id, 'ready', datetime('now'))"
        ),
        {"id": clip_id, "fp": file_path, "fn": os.path.basename(file_path)},
    )


def _seed_scene(
    conn, scene_id: int, clip_id: int = 1, start: float = 0.0, end: float = 5.0
) -> None:
    conn.execute(
        text(
            "INSERT INTO scenes (id, video_clip_id, start_time, end_time) "
            "VALUES (:sid, :cid, :s, :e)"
        ),
        {"sid": scene_id, "cid": clip_id, "s": start, "e": end},
    )


def _seed_run(
    conn,
    run_id: int,
    *,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    audio_track_id: int = 1,
    is_dj_mix: bool = False,
    total_cuts: int = 12,
    total_duration_sec: float = 120.0,
) -> None:
    """Seed a pacing run. ``completed_at=None`` simulates an in-flight run."""
    started_at = started_at or datetime.now(timezone.utc)
    conn.execute(
        text(
            "INSERT INTO mem_pacing_run "
            "(id, audio_track_id, started_at, completed_at, is_dj_mix, "
            " total_duration_sec, total_cuts, agent_version, weights_profile) "
            "VALUES (:id, :aid, :st, :ct, :dj, :dur, :cuts, 'test-v1', "
            "'default')"
        ),
        {
            "id": run_id,
            "aid": audio_track_id,
            "st": started_at,
            "ct": completed_at,
            "dj": 1 if is_dj_mix else 0,
            "dur": total_duration_sec,
            "cuts": total_cuts,
        },
    )


def _seed_decision(
    conn,
    *,
    decision_id: int,
    run_id: int,
    scene_id: int,
    sequence_idx: int,
    at_timestamp_sec: float = 10.0,
    at_section_type: str | None = "drop",
    at_bpm: float | None = 128.0,
    clip_role: str = "hero",
    clip_mood_refined: str = "euphoric",
    clip_style_bucket_id: int = 1,
    agent_score: float = 0.7,
    user_verdict: str | None = None,
    rationale: dict | None = None,
) -> None:
    if rationale is None:
        rationale = {}
    conn.execute(
        text(
            "INSERT INTO mem_decision "
            "(id, run_id, sequence_idx, at_timestamp_sec, at_section_type, "
            " at_bpm, at_enricher_version, scene_id, clip_role, "
            " clip_mood_refined, clip_style_bucket_id, agent_score, "
            " agent_rationale, user_verdict) "
            "VALUES (:id, :rid, :seq, :ts, :section, :bpm, :ver, :sid, "
            ":role, :mood, :bucket, :score, :rat, :verdict)"
        ),
        {
            "id": decision_id,
            "rid": run_id,
            "seq": sequence_idx,
            "ts": at_timestamp_sec,
            "section": at_section_type,
            "bpm": at_bpm,
            "ver": ENRICHER_VERSION,
            "sid": scene_id,
            "role": clip_role,
            "mood": clip_mood_refined,
            "bucket": clip_style_bucket_id,
            "score": agent_score,
            "rat": json.dumps(rationale, sort_keys=True),
            "verdict": user_verdict,
        },
    )


def _ensure_structure_segments_table(conn) -> None:
    """Create the ``structure_segments`` table if the migrated DB doesn't
    already have it.

    The live app bootstraps this table via ``database/migrations.py`` (legacy
    pre-Alembic path), not via Alembic. Tests that go through
    ``_build_struct_db`` only run Alembic, so for segment-strip coverage we
    create the table on demand with the columns referenced by the
    ``list_structure_segments_for_run`` query.
    """
    conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS structure_segments ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  audio_track_id INTEGER NOT NULL,"
            "  start_time REAL NOT NULL,"
            "  end_time REAL NOT NULL,"
            "  label TEXT NOT NULL,"
            "  energy REAL,"
            "  confidence REAL,"
            "  FOREIGN KEY (audio_track_id) REFERENCES audio_tracks(id) "
            "   ON DELETE CASCADE"
            ")"
        )
    )


def _seed_structure_segment(
    conn,
    *,
    segment_id: int,
    audio_track_id: int,
    start_time: float,
    end_time: float,
    label: str = "INTRO",
) -> None:
    _ensure_structure_segments_table(conn)
    conn.execute(
        text(
            "INSERT INTO structure_segments "
            "(id, audio_track_id, start_time, end_time, label) "
            "VALUES (:id, :aid, :st, :et, :lbl)"
        ),
        {
            "id": segment_id,
            "aid": audio_track_id,
            "st": start_time,
            "et": end_time,
            "lbl": label,
        },
    )


def _build_backup_service(tmp_path: Path) -> BackupService:
    db_path = tmp_path / "struct.db"
    backup_dir = tmp_path / "backups"
    return BackupService(db_path=db_path, backup_dir=backup_dir)


# ── BrainService unit tests ───────────────────────────────────────────────────


def test_list_runs_for_audit_selector_only_completed(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        _seed_audio_track(conn, track_id=1)
        # Two completed runs + one in-flight (completed_at=None).
        _seed_run(
            conn,
            run_id=1,
            started_at=now - timedelta(hours=3),
            completed_at=now - timedelta(hours=2, minutes=45),
        )
        _seed_run(
            conn,
            run_id=2,
            started_at=now - timedelta(hours=1),
            completed_at=now - timedelta(minutes=30),
        )
        _seed_run(
            conn,
            run_id=3,
            started_at=now - timedelta(minutes=5),
            completed_at=None,
        )

    svc = BrainService(session_factory=Session)
    runs = svc.list_runs_for_audit_selector()
    ids = [r["id"] for r in runs]
    assert ids == [2, 1]  # newest completed first, no in-flight
    assert all(r["completed_at"] is not None for r in runs)


def test_list_decisions_for_run_sorted_by_sequence_idx(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_audio_track(conn, 1)
        _seed_video_clip(conn, 1)
        for sid in range(1, 6):
            _seed_scene(conn, sid)
        _seed_run(conn, 1, completed_at=datetime.now(timezone.utc))
        # Seed decisions with deliberately-shuffled sequence_idx.
        shuffled_order = [3, 1, 4, 0, 2]
        for decision_id, seq in enumerate(shuffled_order, start=1):
            _seed_decision(
                conn,
                decision_id=decision_id,
                run_id=1,
                scene_id=decision_id,
                sequence_idx=seq,
            )

    svc = BrainService(session_factory=Session)
    cuts = svc.list_decisions_for_run(1)
    assert [c["sequence_idx"] for c in cuts] == [0, 1, 2, 3, 4]


def test_list_decisions_for_run_filter_rejected_only(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_audio_track(conn, 1)
        _seed_video_clip(conn, 1)
        for sid in range(1, 5):
            _seed_scene(conn, sid)
        _seed_run(conn, 1, completed_at=datetime.now(timezone.utc))
        _seed_decision(conn, decision_id=1, run_id=1, scene_id=1, sequence_idx=0)
        _seed_decision(
            conn,
            decision_id=2,
            run_id=1,
            scene_id=2,
            sequence_idx=1,
            user_verdict="reject",
        )
        _seed_decision(conn, decision_id=3, run_id=1, scene_id=3, sequence_idx=2)
        _seed_decision(
            conn,
            decision_id=4,
            run_id=1,
            scene_id=4,
            sequence_idx=3,
            user_verdict="reject",
        )

    svc = BrainService(session_factory=Session)
    cuts = svc.list_decisions_for_run(1, filters={"rejected_only": True})
    assert len(cuts) == 2
    assert all(c["user_verdict"] == "reject" for c in cuts)


def test_list_decisions_for_run_filter_fallback_only(tmp_path: Path) -> None:
    # Documented implementation detail: we use json_extract (SQLite JSON1).
    # Any of fallback / stage1_softened / stage2_forced / forced_negative
    # being truthy counts as "fallback".
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_audio_track(conn, 1)
        _seed_video_clip(conn, 1)
        for sid in (1, 2, 3):
            _seed_scene(conn, sid)
        _seed_run(conn, 1, completed_at=datetime.now(timezone.utc))
        _seed_decision(
            conn,
            decision_id=1,
            run_id=1,
            scene_id=1,
            sequence_idx=0,
            rationale={"fallback": True, "contribs": {"w_role": 0.1}},
        )
        _seed_decision(
            conn,
            decision_id=2,
            run_id=1,
            scene_id=2,
            sequence_idx=1,
            rationale={"contribs": {"w_role": 0.2}},
        )
        _seed_decision(
            conn,
            decision_id=3,
            run_id=1,
            scene_id=3,
            sequence_idx=2,
            rationale={"contribs": {"w_role": 0.3}},
        )

    svc = BrainService(session_factory=Session)
    cuts = svc.list_decisions_for_run(1, filters={"fallback_only": True})
    assert len(cuts) == 1
    assert cuts[0]["id"] == 1


def test_get_decision_detail_parses_rationale(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_audio_track(conn, 1)
        _seed_video_clip(conn, 1)
        _seed_scene(conn, 1)
        _seed_run(conn, 1, completed_at=datetime.now(timezone.utc))
        rationale = {
            "contribs": {"w_role": 0.2, "w_mood_video": 0.1},
            "alternatives": [
                {"scene_id": 7, "score": 0.6, "role": "filler"},
            ],
            "budget_state": {"pending": 2},
            "fallback": False,
        }
        _seed_decision(
            conn,
            decision_id=1,
            run_id=1,
            scene_id=1,
            sequence_idx=0,
            rationale=rationale,
        )

    svc = BrainService(session_factory=Session)
    detail = svc.get_decision_detail(1)
    assert detail is not None
    assert detail["rationale_terms"] == {"w_role": 0.2, "w_mood_video": 0.1}
    assert len(detail["alternatives"]) >= 1
    assert detail["alternatives"][0]["scene_id"] == 7
    assert detail["budget_state"] == {"pending": 2}
    assert detail["fallback"] is False
    assert detail["rejected"] is False


def test_get_decision_detail_alternatives_capped_at_3(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_audio_track(conn, 1)
        _seed_video_clip(conn, 1)
        _seed_scene(conn, 1)
        _seed_run(conn, 1, completed_at=datetime.now(timezone.utc))
        rationale = {
            "contribs": {"w_role": 0.3},
            "alternatives": [
                {"scene_id": i, "score": 0.6 - 0.05 * i, "role": "filler"}
                for i in range(5)
            ],
        }
        _seed_decision(
            conn,
            decision_id=1,
            run_id=1,
            scene_id=1,
            sequence_idx=0,
            rationale=rationale,
        )

    svc = BrainService(session_factory=Session)
    detail = svc.get_decision_detail(1)
    assert detail is not None
    assert len(detail["alternatives"]) == 3


def test_get_decision_detail_returns_none_for_missing_id(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    svc = BrainService(session_factory=Session)
    assert svc.get_decision_detail(9999) is None


def test_list_structure_segments_empty_for_non_dj_mix(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _ensure_structure_segments_table(conn)
        _seed_audio_track(conn, 1)
        _seed_run(
            conn,
            run_id=1,
            completed_at=datetime.now(timezone.utc),
            is_dj_mix=False,
        )
        # A segment exists on the track, but the run is not a DJ-mix.
        _seed_structure_segment(
            conn,
            segment_id=1,
            audio_track_id=1,
            start_time=0.0,
            end_time=30.0,
            label="INTRO",
        )

    svc = BrainService(session_factory=Session)
    assert svc.list_structure_segments_for_run(1) == []


def test_list_structure_segments_for_dj_mix_run_returns_sorted(
    tmp_path: Path,
) -> None:
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_audio_track(conn, 1)
        _seed_run(
            conn,
            run_id=1,
            completed_at=datetime.now(timezone.utc),
            is_dj_mix=True,
        )
        # Seed three segments in shuffled start_time order.
        _seed_structure_segment(
            conn, segment_id=10, audio_track_id=1,
            start_time=60.0, end_time=90.0, label="BUILDUP",
        )
        _seed_structure_segment(
            conn, segment_id=11, audio_track_id=1,
            start_time=0.0, end_time=30.0, label="INTRO",
        )
        _seed_structure_segment(
            conn, segment_id=12, audio_track_id=1,
            start_time=30.0, end_time=60.0, label="VERSE",
        )

    svc = BrainService(session_factory=Session)
    segments = svc.list_structure_segments_for_run(1)
    assert [s["start_sec"] for s in segments] == [0.0, 30.0, 60.0]
    assert [s["label"] for s in segments] == ["INTRO", "VERSE", "BUILDUP"]


# ── AuditTab UI tests ─────────────────────────────────────────────────────────


def test_audit_tab_runs_populate_dropdown(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        _seed_audio_track(conn, 1)
        for rid in (1, 2, 3):
            _seed_run(
                conn,
                run_id=rid,
                started_at=now - timedelta(hours=rid),
                completed_at=now - timedelta(minutes=10 * rid),
            )

    svc = BrainService(session_factory=Session)
    tab = AuditTab(brain_service=svc)
    assert tab._run_selector.run_count() == 3
    assert tab._run_selector._combo.count() == 3


def test_audit_tab_select_run_updates_cut_table(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_audio_track(conn, 1)
        _seed_video_clip(conn, 1)
        for sid in range(1, 5):
            _seed_scene(conn, sid)
        _seed_run(conn, 1, completed_at=datetime.now(timezone.utc))
        for i in range(4):
            _seed_decision(
                conn,
                decision_id=i + 1,
                run_id=1,
                scene_id=i + 1,
                sequence_idx=i,
            )

    svc = BrainService(session_factory=Session)
    tab = AuditTab(brain_service=svc)
    tab.select_run(1)
    assert tab._cut_table.row_count() == 4


def test_audit_tab_filter_rejected_only_hides_accepted(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_audio_track(conn, 1)
        _seed_video_clip(conn, 1)
        for sid in range(1, 5):
            _seed_scene(conn, sid)
        _seed_run(conn, 1, completed_at=datetime.now(timezone.utc))
        _seed_decision(conn, decision_id=1, run_id=1, scene_id=1, sequence_idx=0)
        _seed_decision(
            conn, decision_id=2, run_id=1, scene_id=2,
            sequence_idx=1, user_verdict="reject",
        )
        _seed_decision(conn, decision_id=3, run_id=1, scene_id=3, sequence_idx=2)
        _seed_decision(
            conn, decision_id=4, run_id=1, scene_id=4,
            sequence_idx=3, user_verdict="reject",
        )

    svc = BrainService(session_factory=Session)
    tab = AuditTab(brain_service=svc)
    tab.select_run(1)
    assert tab._cut_table.row_count() == 4

    # Toggle the "rejected only" checkbox → only two rows remain.
    tab._cut_table._rejected_chk.setChecked(True)
    assert tab._cut_table.row_count() == 2


def test_audit_tab_filter_fallback_only_shows_fallback(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_audio_track(conn, 1)
        _seed_video_clip(conn, 1)
        for sid in (1, 2, 3):
            _seed_scene(conn, sid)
        _seed_run(conn, 1, completed_at=datetime.now(timezone.utc))
        _seed_decision(
            conn, decision_id=1, run_id=1, scene_id=1, sequence_idx=0,
            rationale={"fallback": True, "contribs": {"w_role": 0.1}},
        )
        _seed_decision(
            conn, decision_id=2, run_id=1, scene_id=2, sequence_idx=1,
            rationale={"contribs": {"w_role": 0.2}},
        )
        _seed_decision(
            conn, decision_id=3, run_id=1, scene_id=3, sequence_idx=2,
            rationale={"contribs": {"w_role": 0.3}},
        )

    svc = BrainService(session_factory=Session)
    tab = AuditTab(brain_service=svc)
    tab.select_run(1)
    assert tab._cut_table.row_count() == 3

    tab._cut_table._fallback_chk.setChecked(True)
    assert tab._cut_table.row_count() == 1


def test_audit_tab_cut_selection_populates_details(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_audio_track(conn, 1)
        _seed_video_clip(conn, 1)
        _seed_scene(conn, 1)
        _seed_run(conn, 1, completed_at=datetime.now(timezone.utc))
        rationale = {
            "contribs": {
                "w_role": 0.25,
                "w_mood_video": 0.10,
                "w_collision": -0.05,
            },
            "alternatives": [
                {"scene_id": 3, "score": 0.65, "role": "filler"},
                {"scene_id": 4, "score": 0.60, "role": "detail"},
            ],
            "budget_state": {
                "pending_variations_used": 2,
                "active_block": "chorus",
            },
        }
        _seed_decision(
            conn, decision_id=1, run_id=1, scene_id=1, sequence_idx=0,
            rationale=rationale,
        )

    svc = BrainService(session_factory=Session)
    tab = AuditTab(brain_service=svc)
    tab.select_run(1)

    # Select the only row → details column populates.
    tab._cut_table.select_row(0)

    assert tab._term_contributions._bar_count == 3
    assert tab._alternatives.item_count() == 2
    assert tab._budget_state.row_count() == 2


def test_audit_tab_segment_strip_hidden_for_non_dj_mix(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_audio_track(conn, 1)
        _seed_run(
            conn,
            run_id=1,
            completed_at=datetime.now(timezone.utc),
            is_dj_mix=False,
        )

    svc = BrainService(session_factory=Session)
    tab = AuditTab(brain_service=svc)
    tab.select_run(1)
    assert tab._segment_strip.isHidden() is True


def test_audit_tab_segment_strip_visible_for_dj_mix(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_audio_track(conn, 1)
        _seed_run(
            conn,
            run_id=1,
            completed_at=datetime.now(timezone.utc),
            is_dj_mix=True,
            total_duration_sec=180.0,
        )
        _seed_structure_segment(
            conn, segment_id=1, audio_track_id=1,
            start_time=0.0, end_time=60.0, label="INTRO",
        )
        _seed_structure_segment(
            conn, segment_id=2, audio_track_id=1,
            start_time=60.0, end_time=180.0, label="DROP",
        )

    svc = BrainService(session_factory=Session)
    tab = AuditTab(brain_service=svc)
    # Widgets need to be shown at least once for isHidden() to reflect
    # visibility-as-rendered; AuditTab toggles visibility explicitly so the
    # flag is set either way, but we show the tab to match user conditions.
    tab.show()
    tab.select_run(1)
    assert tab._segment_strip.isHidden() is False
    assert tab._segment_strip.segment_count() == 2


def test_memory_tab_runSelected_forwards_to_audit_tab_select_run(
    tmp_path: Path,
) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_audio_track(conn, 1)
        _seed_run(conn, run_id=42, completed_at=datetime.now(timezone.utc))

    svc = BrainService(session_factory=Session)
    backup_svc = _build_backup_service(tmp_path)
    win = StudioBrainWindow.reset_for_test(
        brain_service=svc, backup_service=backup_svc
    )
    try:
        win._memory_tab.runSelected.emit(42)
        assert win._audit_tab._current_run_id == 42
    finally:
        win.close()


def test_studio_brain_window_index_2_is_audit_tab(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)

    svc = BrainService(session_factory=Session)
    backup_svc = _build_backup_service(tmp_path)
    win = StudioBrainWindow.reset_for_test(
        brain_service=svc, backup_service=backup_svc
    )
    try:
        assert win.count_tabs() == 4
        assert type(win._tabs.widget(2)).__name__ == "AuditTab"
        assert win._tabs.tabText(2) == "Audit"
    finally:
        win.close()
