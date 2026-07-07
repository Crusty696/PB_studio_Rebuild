"""Fixplan 2026-07-07 Schritt 1: Motion-Score-Normalisierung + Sampling.

Vorher: min(1.0, raw/40)-Clamp + Frame-Paare mit 1 s Abstand → 41/42 Szenen
saturierten auf exakt 1.0. Diese Tests sichern das neue Verhalten:
saettigungsfreie Kurve, echte Streuung, bewegtes Material > statisches.
"""
import numpy as np
import pytest

from services.video_analysis_service import (
    SceneInfo,
    _cpu_motion_score,
    _normalize_motion,
    compute_motion_scores,
)


class TestNormalizeMotion:
    def test_zero_is_zero(self):
        assert _normalize_motion(0.0) == 0.0
        assert _normalize_motion(-5.0) == 0.0

    def test_measured_raw_values_spread(self):
        """Gemessene 1-Frame-Rohwerte (14–255 px) muessen streuen statt clampen."""
        lo = _normalize_motion(14.48)
        mid = _normalize_motion(29.35)
        hi = _normalize_motion(92.17)
        extreme = _normalize_motion(254.65)
        assert 0.25 < lo < 0.40
        assert 0.45 < mid < 0.60
        assert 0.85 < hi < 0.95
        assert extreme < 1.0  # nie exakt saturiert
        assert lo < mid < hi < extreme

    def test_monotonic(self):
        vals = [_normalize_motion(x) for x in (1, 5, 10, 20, 40, 80, 160, 320)]
        assert vals == sorted(vals)
        assert len(set(vals)) == len(vals)

    def test_old_saturation_case_no_longer_all_one(self):
        """Alt-Bug: raw 41–397 → alle exakt 1.0. Neu: unterscheidbar."""
        a = _normalize_motion(41.42)
        b = _normalize_motion(156.07)
        c = _normalize_motion(397.45)
        assert a < b < c
        assert a < 0.99


def _write_video(path, moving: bool, frames: int = 60, fps: float = 30.0):
    import cv2
    w, h = 320, 240
    vw = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for i in range(frames):
        img = np.zeros((h, w, 3), dtype=np.uint8)
        x = (i * 8) % (w - 60) if moving else 40
        img[80:160, x:x + 60] = 255
        vw.write(img)
    vw.release()


class TestComputeMotionScoresSampling:
    @pytest.fixture()
    def videos(self, tmp_path):
        moving = tmp_path / "moving.mp4"
        static = tmp_path / "static.mp4"
        _write_video(moving, moving=True)
        _write_video(static, moving=False)
        return moving, static

    def test_moving_scores_higher_than_static(self, videos):
        moving, static = videos
        # raft_model_device=(None, None) erzwingt den CPU-Pfad (kein GPU-Load im Test)
        m_scenes = compute_motion_scores(
            str(moving), [SceneInfo(index=0, start_time=0.0, end_time=2.0)],
            raft_model_device=(None, None))
        s_scenes = compute_motion_scores(
            str(static), [SceneInfo(index=0, start_time=0.0, end_time=2.0)],
            raft_model_device=(None, None))
        assert 0.0 <= m_scenes[0].motion_score <= 1.0
        assert 0.0 <= s_scenes[0].motion_score <= 1.0
        assert m_scenes[0].motion_score > s_scenes[0].motion_score
        assert s_scenes[0].motion_score < 0.05

    def test_short_scene_does_not_crash(self, videos):
        moving, _ = videos
        scenes = compute_motion_scores(
            str(moving), [SceneInfo(index=0, start_time=0.0, end_time=0.1)],
            raft_model_device=(None, None))
        assert scenes[0].motion_score is not None


def test_cpu_motion_score_range():
    f1 = np.zeros((240, 320, 3), dtype=np.uint8)
    f2 = np.full((240, 320, 3), 255, dtype=np.uint8)
    assert _cpu_motion_score(f1, f1) == 0.0
    assert _cpu_motion_score(f1, f2) == 1.0
