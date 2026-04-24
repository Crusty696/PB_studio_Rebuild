"""P12 headless tests: StoryMapDialog + BrainService backing methods +
Audit-tab/Timeline triggers + StudioBrainWindow.timelineNavigationRequested.

Mirrors tests/ui/test_audit_tab.py: offscreen Qt + on-disk SQLite migrated
to head via the shared ``_build_struct_db`` helper.
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

from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from services.backup_service import BackupService
from services.brain_service import BrainService
from services.enrichment import ENRICHER_VERSION
from tests.ui.test_audit_tab import (
    _ensure_structure_segments_table,
    _seed_audio_track,
    _seed_run,
    _seed_scene,
    _seed_structure_segment,
    _seed_video_clip,
)
from tests.ui.test_structure_tab import _build_struct_db
from ui.story_map_dialog import StoryMapDialog, _ClipCard
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


def _build_backup_service(tmp_path: Path) -> BackupService:
    return BackupService(
        db_path=tmp_path / "struct.db",
        backup_dir=tmp_path / "backups",
    )


# ── Local seed helper that exercises tension/mood columns ───────────────────


def _seed_decision_with_curves(
    conn,
    *,
    decision_id: int,
    run_id: int,
    scene_id: int,
    sequence_idx: int,
    at_timestamp_sec: float = 10.0,
    at_section_type: str | None = "drop",
    at_mood_audio: str | None = "energetic",
    at_harmonic_tension: float | None = 0.5,
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
            " at_bpm, at_mood_audio, at_harmonic_tension, at_enricher_version, "
            " scene_id, clip_role, clip_mood_refined, clip_style_bucket_id, "
            " agent_score, agent_rationale, user_verdict) "
            "VALUES (:id, :rid, :seq, :ts, :section, :bpm, :mood_aud, "
            ":tension, :ver, :sid, :role, :mood, :bucket, :score, :rat, "
            ":verdict)"
        ),
        {
            "id": decision_id,
            "rid": run_id,
            "seq": sequence_idx,
            "ts": at_timestamp_sec,
            "section": at_section_type,
            "bpm": at_bpm,
            "mood_aud": at_mood_audio,
            "tension": at_harmonic_tension,
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


# ── BrainService unit tests (1–8) ─────────────────────────────────────────────


def test_story_map_data_returns_all_keys(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_audio_track(conn, 1)
        _seed_video_clip(conn, 1)
        for sid in (1, 2, 3):
            _seed_scene(conn, sid)
        _seed_run(
            conn,
            run_id=1,
            completed_at=datetime.now(timezone.utc),
            is_dj_mix=True,
            total_duration_sec=180.0,
        )
        _seed_structure_segment(
            conn, segment_id=1, audio_track_id=1,
            start_time=0.0, end_time=90.0, label="INTRO",
        )
        _seed_structure_segment(
            conn, segment_id=2, audio_track_id=1,
            start_time=90.0, end_time=180.0, label="DROP",
        )
        for i in range(3):
            _seed_decision_with_curves(
                conn,
                decision_id=i + 1,
                run_id=1,
                scene_id=i + 1,
                sequence_idx=i,
                at_timestamp_sec=30.0 * i,
                at_mood_audio=["calm", "energetic", "dramatic"][i],
                at_harmonic_tension=[0.1, 0.4, 0.8][i],
            )

    svc = BrainService(session_factory=Session)
    payload = svc.story_map_data(1)
    assert payload is not None
    expected_keys = {
        "run", "audio_track", "decisions", "structure_segments",
        "tension_curve", "mood_curve", "waveform_energy",
    }
    assert set(payload.keys()) == expected_keys


def test_story_map_data_returns_none_for_missing_run(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    svc = BrainService(session_factory=Session)
    assert svc.story_map_data(9999) is None


def test_story_map_data_decisions_ordered_by_sequence_idx(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_audio_track(conn, 1)
        _seed_video_clip(conn, 1)
        for sid in range(1, 6):
            _seed_scene(conn, sid)
        _seed_run(conn, 1, completed_at=datetime.now(timezone.utc))
        # Insert with shuffled sequence_idx: 3, 1, 4, 0, 2.
        shuffled = [3, 1, 4, 0, 2]
        for did, seq in enumerate(shuffled, start=1):
            _seed_decision_with_curves(
                conn,
                decision_id=did,
                run_id=1,
                scene_id=did,
                sequence_idx=seq,
            )

    svc = BrainService(session_factory=Session)
    payload = svc.story_map_data(1)
    assert payload is not None
    assert [d["sequence_idx"] for d in payload["decisions"]] == [0, 1, 2, 3, 4]


def test_story_map_data_structure_segments_empty_for_non_dj_mix(
    tmp_path: Path,
) -> None:
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
        _seed_structure_segment(
            conn, segment_id=1, audio_track_id=1,
            start_time=0.0, end_time=30.0, label="INTRO",
        )

    svc = BrainService(session_factory=Session)
    payload = svc.story_map_data(1)
    assert payload is not None
    assert payload["structure_segments"] == []


def test_story_map_data_tension_curve_derived_from_decisions(
    tmp_path: Path,
) -> None:
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_audio_track(conn, 1)
        _seed_video_clip(conn, 1)
        for sid in (1, 2, 3):
            _seed_scene(conn, sid)
        _seed_run(conn, 1, completed_at=datetime.now(timezone.utc))
        for i, tension in enumerate([0.1, 0.3, 0.7]):
            _seed_decision_with_curves(
                conn,
                decision_id=i + 1,
                run_id=1,
                scene_id=i + 1,
                sequence_idx=i,
                at_timestamp_sec=10.0 * (i + 1),
                at_harmonic_tension=tension,
            )

    svc = BrainService(session_factory=Session)
    payload = svc.story_map_data(1)
    assert payload is not None
    tension_curve = payload["tension_curve"]
    assert len(tension_curve) == 3
    assert [pytest_round(p["value"], 4) for p in tension_curve] == [0.1, 0.3, 0.7]


def test_story_map_data_mood_curve_derived_from_decisions(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_audio_track(conn, 1)
        _seed_video_clip(conn, 1)
        for sid in (1, 2, 3):
            _seed_scene(conn, sid)
        _seed_run(conn, 1, completed_at=datetime.now(timezone.utc))
        moods = ["calm", "dramatic", "energetic"]
        for i, mood in enumerate(moods):
            _seed_decision_with_curves(
                conn,
                decision_id=i + 1,
                run_id=1,
                scene_id=i + 1,
                sequence_idx=i,
                at_timestamp_sec=5.0 * (i + 1),
                at_mood_audio=mood,
            )

    svc = BrainService(session_factory=Session)
    payload = svc.story_map_data(1)
    assert payload is not None
    mood_curve = payload["mood_curve"]
    assert len(mood_curve) == 3
    assert [p["mood"] for p in mood_curve] == ["calm", "dramatic", "energetic"]


def test_list_runs_with_story_map_data_excludes_runs_without_decisions(
    tmp_path: Path,
) -> None:
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_audio_track(conn, 1)
        _seed_video_clip(conn, 1)
        _seed_scene(conn, 1)
        _seed_run(conn, 1, completed_at=datetime.now(timezone.utc))
        _seed_run(conn, 2, completed_at=datetime.now(timezone.utc))
        # Only run 1 gets a decision.
        _seed_decision_with_curves(
            conn, decision_id=1, run_id=1, scene_id=1, sequence_idx=0
        )

    svc = BrainService(session_factory=Session)
    rows = svc.list_runs_with_story_map_data()
    assert len(rows) == 1
    assert rows[0]["id"] == 1


def test_list_runs_with_story_map_data_sorted_newest_first(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        _seed_audio_track(conn, 1)
        _seed_video_clip(conn, 1)
        for sid in (1, 2, 3):
            _seed_scene(conn, sid)
        _seed_run(conn, 1, started_at=now - timedelta(hours=3),
                  completed_at=now - timedelta(hours=2))
        _seed_run(conn, 2, started_at=now - timedelta(hours=1),
                  completed_at=now - timedelta(minutes=45))
        _seed_run(conn, 3, started_at=now - timedelta(minutes=10),
                  completed_at=now - timedelta(minutes=5))
        for did, rid in enumerate([1, 2, 3], start=1):
            _seed_decision_with_curves(
                conn,
                decision_id=did,
                run_id=rid,
                scene_id=did,
                sequence_idx=0,
            )

    svc = BrainService(session_factory=Session)
    rows = svc.list_runs_with_story_map_data()
    assert [r["id"] for r in rows] == [3, 2, 1]


# ── StoryMapDialog UI tests (9–15) ────────────────────────────────────────────


def _seed_run_with_decisions(
    tmp_path: Path,
    *,
    n_decisions: int = 3,
    is_dj_mix: bool = False,
    total_duration_sec: float = 120.0,
) -> tuple[Any, Any, int]:
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_audio_track(conn, 1, file_path="/mixes/story_map_test.mp3")
        _seed_video_clip(conn, 1)
        for sid in range(1, n_decisions + 1):
            _seed_scene(conn, sid)
        _seed_run(
            conn,
            run_id=1,
            completed_at=datetime.now(timezone.utc),
            is_dj_mix=is_dj_mix,
            total_duration_sec=total_duration_sec,
        )
        for i in range(n_decisions):
            _seed_decision_with_curves(
                conn,
                decision_id=i + 1,
                run_id=1,
                scene_id=i + 1,
                sequence_idx=i,
                at_timestamp_sec=10.0 * (i + 1),
                at_mood_audio=["calm", "energetic", "dramatic"][i % 3],
                at_harmonic_tension=0.2 + i * 0.2,
            )
    return engine, Session, 1


def test_story_map_dialog_instantiates_with_valid_run(tmp_path: Path) -> None:
    _ensure_qapp()
    _engine, Session, run_id = _seed_run_with_decisions(tmp_path)
    svc = BrainService(session_factory=Session)
    dialog = StoryMapDialog(svc, run_id)
    try:
        assert dialog is not None
        assert dialog.data() is not None
    finally:
        dialog.close()
        dialog.deleteLater()


def test_story_map_dialog_header_shows_run_id_and_duration(
    tmp_path: Path,
) -> None:
    _ensure_qapp()
    _engine, Session, run_id = _seed_run_with_decisions(
        tmp_path, total_duration_sec=125.0
    )
    svc = BrainService(session_factory=Session)
    dialog = StoryMapDialog(svc, run_id)
    try:
        header_text = dialog._header.label_text()
        assert f"#{run_id}" in header_text
        assert "02:05" in header_text  # 125s → 02:05
    finally:
        dialog.close()
        dialog.deleteLater()


def test_story_map_dialog_clip_strip_has_one_card_per_decision(
    tmp_path: Path,
) -> None:
    _ensure_qapp()
    _engine, Session, run_id = _seed_run_with_decisions(tmp_path, n_decisions=4)
    svc = BrainService(session_factory=Session)
    dialog = StoryMapDialog(svc, run_id)
    try:
        cards = dialog.findChildren(_ClipCard)
        assert len(cards) == 4
    finally:
        dialog.close()
        dialog.deleteLater()


def test_story_map_dialog_thumbnail_click_emits_signal(tmp_path: Path) -> None:
    _ensure_qapp()
    _engine, Session, run_id = _seed_run_with_decisions(tmp_path)
    svc = BrainService(session_factory=Session)
    dialog = StoryMapDialog(svc, run_id)
    try:
        captured: list[tuple[int, float]] = []
        dialog.thumbnailClicked.connect(
            lambda sid, ts: captured.append((sid, ts))
        )
        cards = dialog.findChildren(_ClipCard)
        assert cards, "expected at least one clip card"
        first_card = cards[0]
        # Simulate via the card's own signal (covers the forward path
        # plus _on_card_clicked → thumbnailClicked.emit).
        first_card.clicked.emit(7, 12.5)
        QApplication.processEvents()
        assert captured == [(7, 12.5)]
    finally:
        dialog.close()
        dialog.deleteLater()


def test_story_map_dialog_export_png_creates_file(tmp_path: Path) -> None:
    _ensure_qapp()
    _engine, Session, run_id = _seed_run_with_decisions(tmp_path)
    svc = BrainService(session_factory=Session)
    dialog = StoryMapDialog(svc, run_id)
    try:
        dialog.show()
        QApplication.processEvents()
        out = tmp_path / "story_map.png"
        result = dialog.export_png(out)
        assert result == out
        assert out.exists()
        assert out.stat().st_size > 0
        # PNG magic bytes: 89 50 4E 47 0D 0A 1A 0A
        with out.open("rb") as fh:
            head = fh.read(8)
        assert head[:8] == b"\x89PNG\r\n\x1a\n"
    finally:
        dialog.close()
        dialog.deleteLater()


def test_story_map_dialog_export_svg_creates_file_or_returns_none(
    tmp_path: Path,
) -> None:
    _ensure_qapp()
    _engine, Session, run_id = _seed_run_with_decisions(tmp_path)
    svc = BrainService(session_factory=Session)
    dialog = StoryMapDialog(svc, run_id)
    try:
        dialog.show()
        QApplication.processEvents()
        out = tmp_path / "story_map.svg"
        try:
            from PySide6.QtSvg import QSvgGenerator  # noqa: F401
            svg_available = True
        except ImportError:
            svg_available = False

        result = dialog.export_svg(out)
        if svg_available:
            assert result == out
            assert out.exists()
            with out.open("r", encoding="utf-8") as fh:
                head = fh.read(200)
            assert "<?xml" in head
            assert "<svg" in head
        else:
            assert result is None
    finally:
        dialog.close()
        dialog.deleteLater()


def test_story_map_dialog_ctrl_wheel_zooms(tmp_path: Path) -> None:
    _ensure_qapp()
    _engine, Session, run_id = _seed_run_with_decisions(tmp_path)
    svc = BrainService(session_factory=Session)
    dialog = StoryMapDialog(svc, run_id)
    try:
        dialog.show()
        QApplication.processEvents()
        master = dialog._linked_plots[0]
        vb = master.getViewBox()
        before = vb.viewRange()[0]
        before_span = float(before[1]) - float(before[0])

        # Direct invocation of the zoom path is the most robust way
        # to assert the contract. Construct a Ctrl+Wheel event too,
        # to cover the wheelEvent slot itself.
        wheel_event = QWheelEvent(
            QPointF(50.0, 50.0),
            QPointF(50.0, 50.0),
            QPoint(0, 120),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.ControlModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        QApplication.sendEvent(dialog, wheel_event)
        QApplication.processEvents()

        after = vb.viewRange()[0]
        after_span = float(after[1]) - float(after[0])
        # Zoomed in (factor 0.8 → narrower span). Use a ratio assertion to
        # avoid float-equal flake.
        assert after_span < before_span

        # Plain wheel (no Ctrl) does NOT zoom.
        baseline = vb.viewRange()[0]
        baseline_span = float(baseline[1]) - float(baseline[0])
        plain_event = QWheelEvent(
            QPointF(50.0, 50.0),
            QPointF(50.0, 50.0),
            QPoint(0, 120),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        QApplication.sendEvent(dialog, plain_event)
        QApplication.processEvents()
        post_plain = vb.viewRange()[0]
        post_plain_span = float(post_plain[1]) - float(post_plain[0])
        assert post_plain_span == pytest.approx(baseline_span, rel=1e-6)
    finally:
        dialog.close()
        dialog.deleteLater()


# ── AuditTab trigger tests (16–17) ────────────────────────────────────────────


def test_audit_tab_story_map_button_opens_dialog_when_run_selected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ensure_qapp()
    _engine, Session, run_id = _seed_run_with_decisions(tmp_path)
    svc = BrainService(session_factory=Session)
    tab = AuditTab(brain_service=svc)
    tab.select_run(run_id)

    captured: list[tuple] = []
    real_init = StoryMapDialog.__init__

    def _spy_init(self, brain_service, rid, parent=None):
        captured.append((rid,))
        real_init(self, brain_service, rid, parent=parent)

    monkeypatch.setattr(StoryMapDialog, "__init__", _spy_init)
    try:
        tab._story_map_btn.click()
        QApplication.processEvents()
        assert len(captured) == 1
        assert captured[0][0] == run_id
    finally:
        for d in list(tab._story_map_dialogs):
            try:
                d.close()
                d.deleteLater()
            except Exception:
                pass
        tab.deleteLater()


def test_audit_tab_story_map_button_shows_info_when_no_run_selected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    # No runs at all → tab settles with current_run_id = None and the
    # selector is disabled.
    svc = BrainService(session_factory=Session)
    tab = AuditTab(brain_service=svc)

    info_calls: list[tuple] = []

    def _spy_info(parent, title, message, *args, **kwargs):
        info_calls.append((title, message))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "information", _spy_info)
    try:
        tab._story_map_btn.click()
        QApplication.processEvents()
        assert len(info_calls) == 1
        title, _msg = info_calls[0]
        assert "Story Map" in title
    finally:
        tab.deleteLater()


# ── StudioBrainWindow signal test (18) ────────────────────────────────────────


def test_studio_brain_window_has_timelineNavigationRequested_signal(
    tmp_path: Path,
) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    svc = BrainService(session_factory=Session)
    backup_svc = _build_backup_service(tmp_path)
    win = StudioBrainWindow.reset_for_test(
        brain_service=svc, backup_service=backup_svc
    )
    try:
        assert hasattr(win, "timelineNavigationRequested")
        captured: list[float] = []
        win.timelineNavigationRequested.connect(lambda ts: captured.append(ts))
        win.timelineNavigationRequested.emit(3.14)
        QApplication.processEvents()
        assert captured == [pytest.approx(3.14)]
    finally:
        win.close()


# ── Helpers ──────────────────────────────────────────────────────────────────


def pytest_round(value: float, ndigits: int) -> float:
    return round(float(value), ndigits)
