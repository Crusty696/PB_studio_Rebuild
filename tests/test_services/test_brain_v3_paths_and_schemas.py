"""Tests fuer services.brain.paths und services.brain.schemas.*.

Zweck: Pfad-Konvention + Schema-Validierung pruefen, OHNE auf System-
APPDATA zu schreiben (TMP-overlay via monkeypatch).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from services.brain import paths
from services.brain.schemas.audio import (
    SubtrackSegment, TempoCurvePoint, BrainV3AudioMeta, SubtrackDetectionResult,
)
from services.brain.schemas.video import (
    CurvePoint, VisualCurves, BrainV3VideoMeta, VisualCurvesResult,
)


# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------
@pytest.fixture
def isolated_appdata(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData_Roaming"))
    yield tmp_path


def test_brain_v3_app_dir_creates_under_appdata(isolated_appdata):
    p = paths.brain_v3_app_dir()
    assert p.exists()
    assert p.name == "brain_v3"
    assert p.parent.name == "PB_Studio"
    assert p.is_relative_to(isolated_appdata)


def test_brain_v3_app_dir_separated_from_v1_v2(isolated_appdata):
    """V3-DBs liegen in eigenem Subfolder, NICHT direkt unter PB_Studio/."""
    p = paths.brain_v3_app_dir()
    pb_root = isolated_appdata / "AppData_Roaming" / "PB_Studio"
    assert p == pb_root / "brain_v3"
    # V1/V2 Hypothese-Pfad waere pb_root / "brain" oder pb_root direkt
    assert p != pb_root / "brain"


def test_db_path_helpers(isolated_appdata):
    assert paths.weights_db_path().name == "weights.db"
    assert paths.patterns_db_path().name == "patterns.db"
    assert paths.embedding_cache_db_path().name == "embedding_cache.db"
    # Alle drei im selben Verzeichnis
    assert paths.weights_db_path().parent == paths.embedding_cache_db_path().parent


def test_project_paths_under_project_root(tmp_path: Path):
    proj = tmp_path / "my_project"
    proj.mkdir()
    p = paths.brain_v3_project_dir(proj)
    assert p == proj / "brain_v3"
    assert p.exists()
    assert paths.project_embeddings_db_path(proj).name == "embeddings.db"
    assert paths.project_state_db_path(proj).name == "state.db"


# ---------------------------------------------------------------------------
# schemas/audio
# ---------------------------------------------------------------------------
HASH64 = "0" * 64


def test_subtrack_segment_validates_times():
    seg = SubtrackSegment(start_time=0.0, end_time=10.0, confidence=0.7)
    assert seg.duration() == 10.0
    # end_time muss > 0
    with pytest.raises(Exception):
        SubtrackSegment(start_time=0.0, end_time=0.0, confidence=0.7)
    # confidence outside 0..1
    with pytest.raises(Exception):
        SubtrackSegment(start_time=0.0, end_time=10.0, confidence=1.5)


def test_subtrack_segment_frozen():
    seg = SubtrackSegment(start_time=0.0, end_time=10.0, confidence=0.7)
    with pytest.raises(Exception):
        seg.start_time = 1.0  # frozen=True


def test_brain_v3_audio_meta_hash_length():
    BrainV3AudioMeta(audio_hash=HASH64)
    with pytest.raises(Exception):
        BrainV3AudioMeta(audio_hash="too_short")
    with pytest.raises(Exception):
        BrainV3AudioMeta(audio_hash="0" * 65)


def test_subtrack_detection_result_default_weights():
    res = SubtrackDetectionResult(
        audio_hash=HASH64, duration_seconds=120.0, n_segments=0,
    )
    assert res.fusion_weights == {
        "foote": 0.35, "stem": 0.30, "tempo": 0.20, "spectral": 0.15,
    }
    assert sum(res.fusion_weights.values()) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# schemas/video
# ---------------------------------------------------------------------------
def test_curve_point_immutable():
    cp = CurvePoint(time=0.0, value=0.5)
    with pytest.raises(Exception):
        cp.value = 0.9


def test_visual_curves_default_sample_rate_is_one_hz():
    vc = VisualCurves(duration_seconds=10.0)
    assert vc.sample_rate_hz == 1.0


def test_brain_v3_video_meta_tag_separation():
    meta = BrainV3VideoMeta(
        video_hash=HASH64,
        mood_tags=["dark"],
        style_tags=["cinematic"],
        object_tags=["person"],
    )
    assert meta.mood_tags == ["dark"]
    assert meta.style_tags == ["cinematic"]
    assert meta.object_tags == ["person"]


def test_visual_curves_result_carries_hash():
    vc = VisualCurves(duration_seconds=5.0)
    r = VisualCurvesResult(
        video_hash=HASH64, duration_seconds=5.0, n_samples=0, curves=vc,
    )
    assert r.video_hash == HASH64
