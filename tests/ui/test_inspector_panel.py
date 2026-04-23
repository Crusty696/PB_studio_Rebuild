"""T10.2b headless tests: InspectorPanel + BrainService.get_clip_detail.

Offscreen Qt + in-memory SQLite (on-disk via tmp_path, same pattern as
tests/ui/test_structure_tab.py). The fixture helpers are imported from
test_structure_tab as a plain module import — they're not exposed as a
pytest conftest so we get tight coupling without fighting fixture scope.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from sqlalchemy import text

from PySide6.QtWidgets import QApplication

from services.brain_service import BrainService
from ui.studio_brain.inspector_panel import InspectorPanel
from ui.studio_brain.structure_tab import StructureTab

# Reuse test_structure_tab's fixture helpers (plain import — no conftest).
from tests.ui.test_structure_tab import (  # noqa: E402
    _build_struct_db,
    _seed_audio_track,
    _seed_basics,
    _seed_bucket,
    _seed_decision,
    _seed_run,
    _seed_scene,
    _seed_tag,
    _seed_video_clip,
)


# ── Qt helper ─────────────────────────────────────────────────────────────────


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ── Local helpers ─────────────────────────────────────────────────────────────


def _seed_edge(
    conn,
    scene_id_a: int,
    scene_id_b: int,
    cosine: float,
    rank: int,
) -> None:
    conn.execute(
        text(
            "INSERT INTO struct_compat_edge "
            "(scene_id_a, scene_id_b, cosine_similarity, rank_in_a) "
            "VALUES (:a, :b, :c, :r)"
        ),
        {"a": scene_id_a, "b": scene_id_b, "c": cosine, "r": rank},
    )


def _seed_run_with_completed_at(conn, run_id: int, completed_at: datetime) -> None:
    conn.execute(
        text(
            "INSERT INTO mem_pacing_run "
            "(id, audio_track_id, started_at, completed_at, is_dj_mix, "
            " total_duration_sec, total_cuts, agent_version, weights_profile) "
            "VALUES (:id, 1, :started, :completed, 0, 120.0, 0, 'test', 'default')"
        ),
        {
            "id": run_id,
            "started": completed_at - timedelta(minutes=1),
            "completed": completed_at,
        },
    )


# ── BrainService.get_clip_detail tests ────────────────────────────────────────


def test_get_clip_detail_returns_full_row(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        _seed_scene(conn, 10, start=12.0, end=18.5)
        _seed_tag(
            conn,
            10,
            role="hero",
            role_conf=0.87,
            mood="euphoric",
            mood_conf=0.72,
            bucket_id=1,
            distance=0.123,
        )

    svc = BrainService(session_factory=Session)
    detail = svc.get_clip_detail(10)
    assert detail is not None

    expected_keys = {
        "scene_id",
        "video_file_basename",
        "start_time",
        "end_time",
        "role",
        "role_confidence",
        "mood_refined",
        "mood_confidence",
        "style_bucket_id",
        "style_bucket_name",
        "style_distance",
        "neighbors",
        "usage_count",
        "last_run_completed_at",
    }
    assert set(detail.keys()) == expected_keys

    assert detail["scene_id"] == 10
    assert detail["video_file_basename"] == "v.mp4"
    assert detail["start_time"] == pytest.approx(12.0)
    assert detail["end_time"] == pytest.approx(18.5)
    assert detail["role"] == "hero"
    assert detail["role_confidence"] == pytest.approx(0.87)
    assert detail["mood_refined"] == "euphoric"
    assert detail["mood_confidence"] == pytest.approx(0.72)
    assert detail["style_bucket_id"] == 1
    assert detail["style_bucket_name"] == "Warm"
    assert detail["style_distance"] == pytest.approx(0.123)
    assert detail["neighbors"] == []
    assert detail["usage_count"] == 0
    assert detail["last_run_completed_at"] is None


def test_get_clip_detail_returns_none_for_unenriched_scene(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_video_clip(conn)
        _seed_audio_track(conn)
        # Scene without tags.
        _seed_scene(conn, 999)

    svc = BrainService(session_factory=Session)
    assert svc.get_clip_detail(999) is None


def test_get_clip_detail_neighbors_are_ordered_by_rank(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        _seed_scene(conn, 10)
        _seed_scene(conn, 20)
        _seed_scene(conn, 30)
        _seed_scene(conn, 40)
        _seed_tag(conn, 10, bucket_id=1)
        _seed_tag(conn, 20, bucket_id=1, role="r20", mood="m20")
        _seed_tag(conn, 30, bucket_id=1, role="r30", mood="m30")
        _seed_tag(conn, 40, bucket_id=1, role="r40", mood="m40")
        _seed_edge(conn, 10, 20, cosine=0.9, rank=1)
        _seed_edge(conn, 10, 30, cosine=0.8, rank=2)
        _seed_edge(conn, 10, 40, cosine=0.7, rank=3)

    svc = BrainService(session_factory=Session)
    detail = svc.get_clip_detail(10)
    assert detail is not None
    ids = [n["scene_id"] for n in detail["neighbors"]]
    assert ids == [20, 30, 40]


def test_get_clip_detail_neighbors_limit_is_5(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        _seed_scene(conn, 10)
        _seed_tag(conn, 10, bucket_id=1)
        for i in range(10):
            nb = 100 + i
            _seed_scene(conn, nb)
            _seed_tag(conn, nb, bucket_id=1)
            _seed_edge(conn, 10, nb, cosine=0.9 - i * 0.05, rank=i + 1)

    svc = BrainService(session_factory=Session)
    detail = svc.get_clip_detail(10)
    assert detail is not None
    assert len(detail["neighbors"]) == 5
    # Order should be the first 5 ranks.
    assert [n["scene_id"] for n in detail["neighbors"]] == [100, 101, 102, 103, 104]


def test_get_clip_detail_neighbor_with_no_tags_row_shows_dashes(
    tmp_path: Path,
) -> None:
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        _seed_scene(conn, 10)
        _seed_scene(conn, 99)  # no tags row
        _seed_tag(conn, 10, bucket_id=1)
        _seed_edge(conn, 10, 99, cosine=0.55, rank=1)

    svc = BrainService(session_factory=Session)
    detail = svc.get_clip_detail(10)
    assert detail is not None
    assert len(detail["neighbors"]) == 1
    n = detail["neighbors"][0]
    assert n["scene_id"] == 99
    assert n["role"] is None
    assert n["mood_refined"] is None
    assert n["cosine_similarity"] == pytest.approx(0.55)


def test_get_clip_detail_usage_count_and_last_run(tmp_path: Path) -> None:
    engine, Session = _build_struct_db(tmp_path)
    with engine.begin() as conn:
        _seed_video_clip(conn)
        _seed_audio_track(conn)
        _seed_bucket(conn, 1, "Warm")
        _seed_scene(conn, 10)
        _seed_tag(conn, 10, bucket_id=1)

        # Two runs with distinct completed_at timestamps.
        old_ts = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
        new_ts = datetime(2026, 4, 20, 15, 30, 0, tzinfo=timezone.utc)
        _seed_run_with_completed_at(conn, run_id=1, completed_at=old_ts)
        _seed_run_with_completed_at(conn, run_id=2, completed_at=new_ts)
        _seed_decision(conn, run_id=1, scene_id=10, sequence_idx=0)
        _seed_decision(conn, run_id=2, scene_id=10, sequence_idx=0)

    svc = BrainService(session_factory=Session)
    detail = svc.get_clip_detail(10)
    assert detail is not None
    assert detail["usage_count"] == 2
    assert detail["last_run_completed_at"] is not None
    # Depending on SQLAlchemy/driver, may be ISO str or ISO-ish. Just verify
    # it matches the newer timestamp's date portion.
    assert "2026-04-20" in detail["last_run_completed_at"]


# ── InspectorPanel widget tests ───────────────────────────────────────────────


def _build_panel_for_scene(
    tmp_path: Path,
    scene_id: int = 10,
    *,
    with_tags: bool = True,
) -> tuple[InspectorPanel, BrainService]:
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        _seed_scene(conn, scene_id, start=10.0, end=15.25)
        if with_tags:
            _seed_tag(
                conn,
                scene_id,
                role="hero",
                role_conf=0.85,
                mood="euphoric",
                mood_conf=0.6,
                bucket_id=1,
            )
    svc = BrainService(session_factory=Session)
    _ensure_qapp()
    panel = InspectorPanel(svc)
    return panel, svc


def test_inspector_populate_repaints_fields(tmp_path: Path) -> None:
    panel, _ = _build_panel_for_scene(tmp_path, scene_id=10, with_tags=True)
    panel.populate(10)

    # Structured form is visible, placeholder hidden.
    assert panel._form_widget.isHidden() is False
    assert panel._status_label.isHidden() is True

    assert panel._scene_id == 10
    assert panel._scene_id_label.text() == "#10"
    assert panel._role_label.text().startswith("hero")
    # 0.85 confidence → "85%"
    assert "85%" in panel._role_label.text()
    assert panel._mood_label.text().startswith("euphoric")
    assert "Warm" in panel._style_label.text()
    assert panel._video_label.text() == "v.mp4"
    # mm:ss.xx format → "00:10.00 – 00:15.25"
    assert "00:10.00" in panel._time_label.text()
    assert "00:15.25" in panel._time_label.text()


def test_inspector_unenriched_scene_shows_graceful_message(tmp_path: Path) -> None:
    panel, _ = _build_panel_for_scene(tmp_path, scene_id=10, with_tags=False)
    panel.populate(10)

    assert panel._status_label.isHidden() is False
    assert panel._form_widget.isHidden() is True
    status_text = panel._status_label.text().lower()
    assert "not enriched" in status_text
    assert "#10" in panel._status_label.text()


def test_inspector_clear_resets_to_placeholder(tmp_path: Path) -> None:
    panel, _ = _build_panel_for_scene(tmp_path, scene_id=10, with_tags=True)
    panel.populate(10)
    assert panel._form_widget.isHidden() is False

    panel.clear()
    assert panel._scene_id is None
    assert panel._status_label.isHidden() is False
    assert panel._form_widget.isHidden() is True
    assert panel._status_label.text().lower().startswith("select")


def test_structure_tab_clipSelected_populates_inspector(tmp_path: Path) -> None:
    _ensure_qapp()
    engine, Session = _build_struct_db(tmp_path)
    _seed_basics(engine)
    with engine.begin() as conn:
        _seed_bucket(conn, 1, "Warm")
        _seed_scene(conn, 77)
        _seed_tag(conn, 77, bucket_id=1, role="hero")

    svc = BrainService(session_factory=Session)
    tab = StructureTab(brain_service=svc)

    # Simulate a card click (or any external emitter).
    tab.clipSelected.emit(77)

    assert tab._inspector._scene_id == 77
    assert tab._inspector._form_widget.isHidden() is False
    assert tab._inspector._scene_id_label.text() == "#77"
    assert tab._inspector._role_label.text().startswith("hero")
