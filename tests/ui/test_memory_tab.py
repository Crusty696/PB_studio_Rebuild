"""T11.1 headless tests: MemoryTab (run-timeline + pattern table + drill-down)
and the BrainService reads backing it.

Follows the offscreen-Qt + on-disk-SQLite pattern established in
tests/ui/test_structure_tab.py. The ``_build_struct_db`` helper is reused
directly — it already migrates the DB to head so ``mem_pacing_run``,
``mem_decision`` and ``mem_learned_pattern`` exist.
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

from PySide6.QtWidgets import QApplication, QMessageBox

from services.backup_service import BackupService
from services.brain import BrainService
from services.enrichment import ENRICHER_VERSION
from tests.ui.test_structure_tab import _build_struct_db
from ui.studio_brain.memory_tab import MemoryTab, _get_memory_reset_pool
from ui.studio_brain_window import StudioBrainWindow


# ── Qt + singleton hygiene ────────────────────────────────────────────────────


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _wait_for_reset_pool(app: QApplication) -> None:
    """B-641: Reset laeuft jetzt im QThreadPool (off GUI-Thread) statt
    synchron. Test muss auf den Pool-Job + die QueuedConnection-Zustellung
    des done-Signals warten, statt das Ergebnis direkt nach .click() zu
    erwarten."""
    _get_memory_reset_pool().waitForDone(5000)
    for _ in range(20):
        app.processEvents()


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


# ── Seed helpers (memory-layer specific) ──────────────────────────────────────


def _seed_audio_track(
    conn, track_id: int = 1, file_path: str = "/mixes/set_01.mp3"
) -> None:
    conn.execute(
        text(
            "INSERT INTO audio_tracks (id, file_path, original_filename, "
            "sha256, status, created_at) "
            "VALUES (:id, :fp, :fn, 'a-sha', 'ready', datetime('now'))"
        ),
        {"id": track_id, "fp": file_path, "fn": os.path.basename(file_path)},
    )


def _seed_video_clip(conn, clip_id: int = 1) -> None:
    conn.execute(
        text(
            "INSERT INTO video_clips (id, file_path, original_filename, "
            "sha256, status, created_at) "
            "VALUES (:id, '/v.mp4', 'v.mp4', 'v-sha', 'ready', datetime('now'))"
        ),
        {"id": clip_id},
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
    started_at: datetime,
    *,
    audio_track_id: int = 1,
    is_dj_mix: bool = False,
    user_rating: int | None = None,
    total_cuts: int = 12,
) -> None:
    conn.execute(
        text(
            "INSERT INTO mem_pacing_run "
            "(id, audio_track_id, started_at, is_dj_mix, "
            " total_duration_sec, total_cuts, agent_version, weights_profile, "
            " user_rating) "
            "VALUES (:id, :aid, :ts, :dj, 120.0, :cuts, 'test-v1', "
            "'default', :ur)"
        ),
        {
            "id": run_id,
            "aid": audio_track_id,
            "ts": started_at,
            "dj": 1 if is_dj_mix else 0,
            "cuts": total_cuts,
            "ur": user_rating,
        },
    )


def _seed_pattern(
    conn,
    *,
    pattern_id: int,
    pattern_type: str = "context_preference",
    fingerprint: dict | None = None,
    target_scene_id: int = 1,
    accept: int = 5,
    reject: int = 1,
    confidence: float = 0.5,
    last_updated: datetime | None = None,
) -> None:
    fp = fingerprint if fingerprint is not None else {
        "genre": "house",
        "section_type": "drop",
        "bpm_bucket": "128",
    }
    tr = {"scene_id": int(target_scene_id)}
    ts = last_updated if last_updated is not None else datetime.now(timezone.utc)
    conn.execute(
        text(
            "INSERT INTO mem_learned_pattern "
            "(id, pattern_type, context_fingerprint, target_ref, "
            " stat_accept_count, stat_reject_count, stat_sample_size, "
            " confidence, last_updated) "
            "VALUES (:id, :ptype, :fp, :tr, :a, :r, :s, :c, :ts)"
        ),
        {
            "id": pattern_id,
            "ptype": pattern_type,
            "fp": json.dumps(fp, sort_keys=True),
            "tr": json.dumps(tr, sort_keys=True),
            "a": accept,
            "r": reject,
            "s": accept + reject,
            "c": confidence,
            "ts": ts,
        },
    )


def _seed_decision(
    conn,
    *,
    decision_id: int,
    run_id: int,
    scene_id: int,
    sequence_idx: int,
    at_timestamp_sec: float,
    at_bpm: float | None,
    at_genre: str | None,
    at_section_type: str | None,
    at_enricher_version: str | None = ENRICHER_VERSION,
    user_verdict: str | None = None,
) -> None:
    conn.execute(
        text(
            "INSERT INTO mem_decision "
            "(id, run_id, sequence_idx, at_timestamp_sec, at_bpm, "
            " at_genre, at_section_type, at_enricher_version, scene_id, "
            " clip_role, clip_mood_refined, clip_style_bucket_id, "
            " agent_score, agent_rationale, user_verdict) "
            "VALUES (:id, :rid, :seq, :ts, :bpm, :genre, :section, :ver, "
            ":sid, 'hero', 'euphoric', 1, 0.7, '{}', :verdict)"
        ),
        {
            "id": decision_id,
            "rid": run_id,
            "seq": sequence_idx,
            "ts": at_timestamp_sec,
            "bpm": at_bpm,
            "genre": at_genre,
            "section": at_section_type,
            "ver": at_enricher_version,
            "sid": scene_id,
            "verdict": user_verdict,
        },
    )


# ── BrainService unit tests ───────────────────────────────────────────────────


def test_list_pacing_runs_reverse_chronological(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        _seed_audio_track(conn, track_id=1)
        _seed_run(conn, run_id=1, started_at=now - timedelta(hours=5))
        _seed_run(conn, run_id=2, started_at=now - timedelta(hours=2))
        _seed_run(conn, run_id=3, started_at=now - timedelta(hours=10))

    svc = BrainService(session_factory=Session)
    runs = svc.list_pacing_runs()
    assert [r["id"] for r in runs] == [2, 1, 3]


def test_list_pacing_runs_joins_audio_track_filename(tmp_path: Path) -> None:
    """The joined ``audio_track_filename`` is the raw ``file_path``; callers
    (or the UI) are free to basename-strip it for display. Matching spec
    leeway: asserts the raw path value is present."""
    engine, Session = _build_struct_db(tmp_path)
    path = "/mixes/summer_set.mp3"
    with engine.begin() as conn:
        _seed_audio_track(conn, track_id=1, file_path=path)
        _seed_run(conn, run_id=1, started_at=datetime.now(timezone.utc))

    svc = BrainService(session_factory=Session)
    runs = svc.list_pacing_runs()
    assert len(runs) == 1
    assert runs[0]["audio_track_filename"] == path


def test_list_learned_patterns_sorted_confidence_desc(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_pattern(conn, pattern_id=1, confidence=0.2)
        _seed_pattern(conn, pattern_id=2, confidence=0.8)
        _seed_pattern(conn, pattern_id=3, confidence=0.5)

    svc = BrainService(session_factory=Session)
    patterns = svc.list_learned_patterns()
    assert [p["id"] for p in patterns] == [2, 3, 1]
    confidences = [p["confidence"] for p in patterns]
    assert confidences == sorted(confidences, reverse=True)


def test_list_learned_patterns_filter_by_type(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_pattern(conn, pattern_id=1, pattern_type="harmonic", confidence=0.5)
        _seed_pattern(conn, pattern_id=2, pattern_type="harmonic", confidence=0.4)
        _seed_pattern(conn, pattern_id=3, pattern_type="style", confidence=0.9)

    svc = BrainService(session_factory=Session)
    patterns = svc.list_learned_patterns(pattern_type="harmonic")
    assert len(patterns) == 2
    assert all(p["pattern_type"] == "harmonic" for p in patterns)


def test_list_learned_patterns_filter_by_min_confidence(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_pattern(conn, pattern_id=1, confidence=0.2)
        _seed_pattern(conn, pattern_id=2, confidence=0.8)
        _seed_pattern(conn, pattern_id=3, confidence=0.5)

    svc = BrainService(session_factory=Session)
    patterns = svc.list_learned_patterns(min_confidence=0.5)
    assert len(patterns) == 2
    assert all(p["confidence"] >= 0.5 for p in patterns)


def test_list_decisions_for_pattern_matches_fingerprint_triple(
    tmp_path: Path,
) -> None:
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_audio_track(conn, track_id=1)
        _seed_video_clip(conn, clip_id=1)
        for sid in (1, 2, 3, 4):
            _seed_scene(conn, sid)
        _seed_run(conn, run_id=1, started_at=datetime.now(timezone.utc))
        _seed_pattern(
            conn,
            pattern_id=1,
            fingerprint={
                "genre": "house",
                "section_type": "drop",
                "bpm_bucket": "128",
            },
        )
        # 2 matching decisions (bpm 127.8 and 128.2 both round to 128).
        _seed_decision(
            conn, decision_id=1, run_id=1, scene_id=1, sequence_idx=0,
            at_timestamp_sec=5.0, at_bpm=127.8, at_genre="house",
            at_section_type="drop",
        )
        _seed_decision(
            conn, decision_id=2, run_id=1, scene_id=2, sequence_idx=1,
            at_timestamp_sec=10.0, at_bpm=128.2, at_genre="house",
            at_section_type="drop",
        )
        # 2 non-matching decisions (wrong genre; wrong section).
        _seed_decision(
            conn, decision_id=3, run_id=1, scene_id=3, sequence_idx=2,
            at_timestamp_sec=15.0, at_bpm=128.0, at_genre="techno",
            at_section_type="drop",
        )
        _seed_decision(
            conn, decision_id=4, run_id=1, scene_id=4, sequence_idx=3,
            at_timestamp_sec=20.0, at_bpm=128.0, at_genre="house",
            at_section_type="buildup",
        )

    svc = BrainService(session_factory=Session)
    decisions = svc.list_decisions_for_pattern(1)
    assert len(decisions) == 2
    assert {d["decision_id"] for d in decisions} == {1, 2}


def test_list_distinct_pattern_types(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_pattern(conn, pattern_id=1, pattern_type="c")
        _seed_pattern(conn, pattern_id=2, pattern_type="a")
        _seed_pattern(conn, pattern_id=3, pattern_type="b")

    svc = BrainService(session_factory=Session)
    assert svc.list_distinct_pattern_types() == ["a", "b", "c"]


# ── MemoryTab UI tests ────────────────────────────────────────────────────────


def _build_backup_service(tmp_path: Path) -> BackupService:
    """Wire a BackupService to a real on-disk SQLite + a tmp backup dir."""
    # The actual DB file lives at tmp_path/struct.db (from _build_struct_db).
    db_path = tmp_path / "struct.db"
    backup_dir = tmp_path / "backups"
    return BackupService(db_path=db_path, backup_dir=backup_dir)


def test_memory_tab_run_timeline_shows_all_runs(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        _seed_audio_track(conn, track_id=1)
        _seed_run(conn, run_id=1, started_at=now - timedelta(hours=3))
        _seed_run(conn, run_id=2, started_at=now - timedelta(hours=2))
        _seed_run(conn, run_id=3, started_at=now - timedelta(hours=1))

    svc = BrainService(session_factory=Session)
    tab = MemoryTab(
        brain_service=svc,
        backup_service=_build_backup_service(tmp_path),
    )
    assert tab._timeline.frame_count() == 3


def test_memory_tab_pattern_table_renders_rows(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_pattern(conn, pattern_id=1, confidence=0.7)
        _seed_pattern(conn, pattern_id=2, confidence=0.3)

    svc = BrainService(session_factory=Session)
    tab = MemoryTab(
        brain_service=svc,
        backup_service=_build_backup_service(tmp_path),
    )
    assert tab._pattern_table.row_count() == 2


def test_memory_tab_filter_change_refreshes_patterns(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_pattern(conn, pattern_id=1, pattern_type="harmonic", confidence=0.5)
        _seed_pattern(conn, pattern_id=2, pattern_type="style", confidence=0.5)

    svc = BrainService(session_factory=Session)
    tab = MemoryTab(
        brain_service=svc,
        backup_service=_build_backup_service(tmp_path),
    )
    # Initial: both types rendered.
    assert tab._pattern_table.row_count() == 2

    # Change filter → only "harmonic" visible.
    tab._pattern_table.set_type_filter("harmonic")
    tab._pattern_table._emit_apply()
    assert tab._pattern_table.row_count() == 1


def test_memory_tab_pattern_selection_populates_drill_down(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_audio_track(conn, track_id=1)
        _seed_video_clip(conn, clip_id=1)
        _seed_scene(conn, 10)
        _seed_scene(conn, 11)
        _seed_run(conn, run_id=1, started_at=datetime.now(timezone.utc))
        _seed_pattern(
            conn,
            pattern_id=1,
            fingerprint={
                "genre": "house",
                "section_type": "drop",
                "bpm_bucket": "128",
            },
        )
        _seed_decision(
            conn, decision_id=1, run_id=1, scene_id=10, sequence_idx=0,
            at_timestamp_sec=5.0, at_bpm=128.0, at_genre="house",
            at_section_type="drop",
        )
        _seed_decision(
            conn, decision_id=2, run_id=1, scene_id=11, sequence_idx=1,
            at_timestamp_sec=10.0, at_bpm=128.0, at_genre="house",
            at_section_type="drop",
        )

    svc = BrainService(session_factory=Session)
    tab = MemoryTab(
        brain_service=svc,
        backup_service=_build_backup_service(tmp_path),
    )
    tab._pattern_table.select_row(0)
    assert tab._drill_down.item_count() == 2


def test_memory_tab_reset_creates_backup_and_deletes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_pattern(conn, pattern_id=1, confidence=0.2)
        _seed_pattern(conn, pattern_id=2, confidence=0.5)
        _seed_pattern(conn, pattern_id=3, confidence=0.9)

    svc = BrainService(session_factory=Session)
    backup_svc = _build_backup_service(tmp_path)

    # Spy on BackupService.backup while still calling through so the backup
    # file actually materialises and the destructive SQL runs inside the
    # yield'd context manager.
    call_log: list[dict[str, Any]] = []
    real_backup = BackupService.backup

    def _spy_backup(self, reason: str = "manual"):
        call_log.append({"reason": reason})
        return real_backup(self, reason=reason)

    monkeypatch.setattr(BackupService, "backup", _spy_backup)

    # Auto-confirm the QMessageBox.question dialog.
    monkeypatch.setattr(
        "PySide6.QtWidgets.QMessageBox.question",
        lambda *a, **k: QMessageBox.StandardButton.Yes,
    )

    tab = MemoryTab(brain_service=svc, backup_service=backup_svc)

    received: list[int] = []
    tab.patternsReset.connect(received.append)

    tab._footer._reset_btn.click()
    _wait_for_reset_pool(app)

    # 1) BackupService.backup called exactly once — by pattern_reset_context.
    assert len(call_log) == 1
    assert call_log[0]["reason"] == "learned_patterns_reset"

    # 2) mem_learned_pattern is now empty.
    with engine.begin() as conn:
        remaining = conn.execute(
            text("SELECT COUNT(*) FROM mem_learned_pattern")
        ).scalar()
    assert remaining == 0

    # 3) Signal fired with the deletion count.
    assert received == [3]


def test_memory_tab_reset_cancelled_if_user_declines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_pattern(conn, pattern_id=1, confidence=0.5)

    svc = BrainService(session_factory=Session)
    backup_svc = _build_backup_service(tmp_path)

    call_log: list[dict[str, Any]] = []
    real_backup = BackupService.backup

    def _spy_backup(self, reason: str = "manual"):
        call_log.append({"reason": reason})
        return real_backup(self, reason=reason)

    monkeypatch.setattr(BackupService, "backup", _spy_backup)

    # User declines — No.
    monkeypatch.setattr(
        "PySide6.QtWidgets.QMessageBox.question",
        lambda *a, **k: QMessageBox.StandardButton.No,
    )

    tab = MemoryTab(brain_service=svc, backup_service=backup_svc)

    received: list[int] = []
    tab.patternsReset.connect(received.append)

    tab._footer._reset_btn.click()

    # No backup, no delete, no signal emission.
    assert call_log == []
    with engine.begin() as conn:
        remaining = conn.execute(
            text("SELECT COUNT(*) FROM mem_learned_pattern")
        ).scalar()
    assert remaining == 1
    assert received == []


def test_studio_brain_window_index_1_is_memory_tab(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)

    svc = BrainService(session_factory=Session)
    backup_svc = _build_backup_service(tmp_path)
    win = StudioBrainWindow.reset_for_test(
        brain_service=svc, backup_service=backup_svc
    )
    try:
        # B-184: 6 Tabs seit Cycle 11 / D-023 (Pacing-Explorer + Graph-Cockpit).
        assert win.count_tabs() == 6
        assert type(win._tabs.widget(1)).__name__ == "MemoryTab"
        assert win._tabs.tabText(1) == "Gedächtnis"
    finally:
        win.close()
