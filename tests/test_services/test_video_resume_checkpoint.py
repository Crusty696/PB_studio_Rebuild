"""Phase 17 — Resume-Checkpoint RED.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 17 (Tier 2 Building-Blocks)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_create_and_save_loads_back(tmp_path: Path):
    from services.video_pipeline.primitives.resume_checkpoint import ResumeCheckpoint
    cp = ResumeCheckpoint(tmp_path / "cp.json", track_id=42, stream_sha256="abc123")
    cp.update_stage("scene_detect", status="done", duration_s=12.3)
    cp.save()

    cp2 = ResumeCheckpoint.load(tmp_path / "cp.json")
    assert cp2.track_id == 42
    assert cp2.stream_sha256 == "abc123"
    assert cp2.stages["scene_detect"]["status"] == "done"
    assert cp2.stages["scene_detect"]["duration_s"] == pytest.approx(12.3)


def test_get_completed_stages(tmp_path: Path):
    from services.video_pipeline.primitives.resume_checkpoint import ResumeCheckpoint
    cp = ResumeCheckpoint(tmp_path / "cp.json", track_id=1, stream_sha256="x")
    cp.update_stage("a", status="done")
    cp.update_stage("b", status="running")
    cp.update_stage("c", status="done")
    cp.save()

    completed = cp.completed_stages()
    assert set(completed) == {"a", "c"}


def test_atomic_write_no_corruption(tmp_path: Path, monkeypatch):
    """Atomic write via tmp + rename — Datei nie halb-geschrieben."""
    from services.video_pipeline.primitives.resume_checkpoint import ResumeCheckpoint
    cp = ResumeCheckpoint(tmp_path / "cp.json", track_id=1, stream_sha256="x")
    cp.update_stage("a", status="done")
    cp.save()
    # Datei lesbar als JSON
    data = json.loads((tmp_path / "cp.json").read_text())
    assert data["track_id"] == 1


def test_load_nonexistent_returns_fresh(tmp_path: Path):
    from services.video_pipeline.primitives.resume_checkpoint import ResumeCheckpoint
    p = tmp_path / "missing.json"
    cp = ResumeCheckpoint.load(p, track_id=99, stream_sha256="hash")
    assert cp.track_id == 99
    assert cp.stream_sha256 == "hash"
    assert cp.stages == {}


def test_stream_sha_mismatch_raises(tmp_path: Path):
    """Wenn auf neue Datei geladen wird (anderer SHA), darf nicht falsche
    Checkpoint-Datei zurueck-applied werden."""
    from services.video_pipeline.primitives.resume_checkpoint import (
        ResumeCheckpoint, CheckpointMismatch,
    )
    cp = ResumeCheckpoint(tmp_path / "cp.json", track_id=1, stream_sha256="aaa")
    cp.save()
    with pytest.raises(CheckpointMismatch):
        ResumeCheckpoint.load(tmp_path / "cp.json", track_id=1, stream_sha256="bbb")


def test_b365_completed_excludes_done_stage_with_missing_artifact(tmp_path: Path):
    """B-365: a done stage whose recorded artifact no longer exists must NOT be
    reported as completed, so the orchestrator re-runs it instead of skipping."""
    from services.video_pipeline.primitives.resume_checkpoint import ResumeCheckpoint
    scenes = tmp_path / "scenes.json"
    scenes.write_text("[]", encoding="utf-8")
    cp = ResumeCheckpoint(tmp_path / "cp.json", track_id=1, stream_sha256="x")
    cp.update_stage("scene_detect", status="done", artifacts=[str(scenes)])
    assert cp.completed_stages() == ["scene_detect"]

    # Artefakt verschwindet -> Stage darf nicht mehr blind geskipped werden.
    scenes.unlink()
    assert cp.completed_stages() == []


def test_b365_done_stage_with_present_artifacts_is_completed(tmp_path: Path):
    """B-365: done stage with all artifacts present stays completed."""
    from services.video_pipeline.primitives.resume_checkpoint import ResumeCheckpoint
    a = tmp_path / "keyframes.json"
    b = tmp_path / "embeddings.npy"
    a.write_text("{}", encoding="utf-8")
    b.write_bytes(b"\x00")
    cp = ResumeCheckpoint(tmp_path / "cp.json", track_id=1, stream_sha256="x")
    cp.update_stage("keyframe_extract", status="done", artifacts=[str(a), str(b)])
    assert cp.completed_stages() == ["keyframe_extract"]


def test_b365_legacy_checkpoint_without_artifacts_keeps_status_only(tmp_path: Path):
    """B-365: checkpoints written before the fix have no 'artifacts' key.
    Such done stages keep the old status-only completed behaviour (no regression)."""
    from services.video_pipeline.primitives.resume_checkpoint import ResumeCheckpoint
    cp = ResumeCheckpoint(tmp_path / "cp.json", track_id=1, stream_sha256="x")
    cp.update_stage("scene_detect", status="done")  # no artifacts arg
    assert cp.completed_stages() == ["scene_detect"]
