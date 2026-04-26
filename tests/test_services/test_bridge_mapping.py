"""P1.1 / Cycle 11: Bridge-Mapping zwischen auto_edit_phase3 und PacingPipeline.

Konvertiert die Cut-Loop-Variablen (audio_track, seg_start, sections,
energy_per_beat, video_info, scenes) in ClipFeatures + AudioContext.
"""
from __future__ import annotations

import numpy as np
import pytest

from services.pacing.bridge_mapping import (
    build_audio_context,
    build_clip_features,
)
from services.pacing.scorer import AudioContext, ClipFeatures


class _StubAudioTrack:
    def __init__(self, **kwargs):
        # Defaults mit override
        self.id = kwargs.get("id", 1)
        self.bpm = kwargs.get("bpm", 128.0)
        self.key = kwargs.get("key", "Am")
        self.key_confidence = kwargs.get("key_confidence", 0.9)
        self.mood = kwargs.get("mood", "energetic")
        self.genre = kwargs.get("genre", "psytrance")
        self.sub_genre = kwargs.get("sub_genre", "progressive_psy")
        self.lufs = kwargs.get("lufs", -8.5)
        # Cycle 14 Option A: groove_template lebt jetzt auf beatgrid, nicht
        # direkt auf audio_track. Dual-Set für Backward-Compat.
        self.beatgrid = type("_Bg", (), {
            "groove_template": kwargs.get("groove_template", "fotf"),
        })()
        self.spectral_hash = kwargs.get("spectral_hash", "hash_drop")


class _StubScene:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 100)
        self.motion_score = kwargs.get("motion_score", 0.7)
        self.energy = kwargs.get("energy", 0.7)
        self.ai_mood = kwargs.get("ai_mood", "energetic")
        self.role = kwargs.get("role", "hero")
        self.style_bucket_id = kwargs.get("style_bucket_id", 3)
        self.embedding = kwargs.get("embedding", None)


# ── AudioContext Builder ───────────────────────────────────────────────────


def test_build_audio_context_basic_fields():
    track = _StubAudioTrack()
    beats = np.array([0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0])
    ctx = build_audio_context(
        seg_start_sec=2.0,
        seg_section_type="drop",
        audio_track=track,
        beats=beats,
        energy_per_beat=[0.2, 0.3, 0.5, 0.6, 0.9, 0.8, 0.7],
    )
    assert isinstance(ctx, AudioContext)
    assert ctx.at_timestamp_sec == 2.0
    assert ctx.at_section_type == "drop"
    assert ctx.at_bpm == 128.0
    assert ctx.at_key == "Am"
    assert ctx.at_mood_audio == "energetic"
    assert ctx.at_genre == "psytrance"
    assert ctx.at_sub_genre == "progressive_psy"
    assert ctx.at_lufs == -8.5
    assert ctx.at_groove_template == "fotf"


def test_build_audio_context_beat_idx_and_energy():
    track = _StubAudioTrack(bpm=120.0)
    beats = np.array([0.0, 0.5, 1.0, 1.5, 2.0])
    energy = [0.1, 0.3, 0.6, 0.8, 0.9]
    # seg_start=1.5 → beat_idx=3 → energy=0.8
    ctx = build_audio_context(
        seg_start_sec=1.5,
        seg_section_type="buildup",
        audio_track=track,
        beats=beats,
        energy_per_beat=energy,
    )
    assert ctx.at_beat_idx == 3
    assert ctx.at_energy == 0.8


def test_build_audio_context_energy_clamp_when_beat_idx_oob():
    track = _StubAudioTrack()
    beats = np.array([0.0, 1.0, 2.0])
    energy = [0.5, 0.6]  # nur 2 Einträge
    ctx = build_audio_context(
        seg_start_sec=2.5,  # nach letztem Beat
        seg_section_type="outro",
        audio_track=track,
        beats=beats,
        energy_per_beat=energy,
    )
    # Sollte nicht crashen, energy auf valid Wert clampen
    assert ctx.at_energy is not None
    assert 0.0 <= ctx.at_energy <= 1.0


def test_build_audio_context_handles_missing_track_fields():
    """Audio-Track ohne sub_genre/groove_template → None einsetzen, nicht crashen."""
    class _Sparse:
        id = 1
        bpm = 128.0
        key = None
        key_confidence = None
        mood = None
        genre = None
        lufs = None
    ctx = build_audio_context(
        seg_start_sec=0.0,
        seg_section_type="intro",
        audio_track=_Sparse(),
        beats=np.array([0.0, 0.5]),
        energy_per_beat=[0.1, 0.2],
    )
    assert ctx.at_key is None
    assert ctx.at_genre is None
    assert ctx.at_sub_genre is None
    assert ctx.at_groove_template is None


def test_build_audio_context_section_type_lowercased():
    track = _StubAudioTrack()
    ctx = build_audio_context(
        seg_start_sec=0.0,
        seg_section_type="DROP",
        audio_track=track,
        beats=np.array([0.0]),
        energy_per_beat=[0.5],
    )
    assert ctx.at_section_type == "drop"


def test_build_audio_context_harmonic_tension_from_energy():
    """harmonic_tension wird aus Energy abgeleitet wenn nicht explizit."""
    track = _StubAudioTrack()
    ctx = build_audio_context(
        seg_start_sec=0.0,
        seg_section_type="drop",
        audio_track=track,
        beats=np.array([0.0]),
        energy_per_beat=[0.95],
    )
    # Tension proportional zu energy → in [0, 1]
    assert ctx.at_harmonic_tension is not None
    assert 0.0 <= ctx.at_harmonic_tension <= 1.0
    assert ctx.at_harmonic_tension >= 0.5  # high energy → high tension


# ── ClipFeatures Builder ───────────────────────────────────────────────────


def test_build_clip_features_basic():
    scene = _StubScene(motion_score=0.7, ai_mood="energetic", role="hero")
    cf = build_clip_features(video_clip_id=42, scene=scene)
    assert isinstance(cf, ClipFeatures)
    assert cf.clip_id == 42
    assert cf.scene_id == 100
    assert cf.role == "hero"
    assert cf.mood_refined == "energetic"
    assert cf.motion_score == 0.7


def test_build_clip_features_with_embedding():
    emb = np.zeros(1152, dtype=np.float32)
    emb[0] = 1.0
    scene = _StubScene(embedding=emb)
    cf = build_clip_features(video_clip_id=1, scene=scene)
    assert cf.embedding is not None
    assert cf.embedding.shape == (1152,)


def test_build_clip_features_defaults_when_scene_attrs_missing():
    """Scene ohne ai_mood/role → 'unknown' fallback, nicht crashen."""
    class _Sparse:
        id = 5
        motion_score = 0.5
    cf = build_clip_features(video_clip_id=1, scene=_Sparse())
    assert cf.role == "unknown"
    assert cf.mood_refined == "unknown"
    assert cf.style_bucket_id == 0  # Sentinel für unbekannte Bucket
    assert cf.embedding is None


def test_build_clip_features_motion_score_clamped_zero_one():
    scene = _StubScene(motion_score=2.5)
    cf = build_clip_features(video_clip_id=1, scene=scene)
    assert 0.0 <= cf.motion_score <= 1.0

    scene2 = _StubScene(motion_score=-0.3)
    cf2 = build_clip_features(video_clip_id=1, scene=scene2)
    assert 0.0 <= cf2.motion_score <= 1.0


def test_build_clip_features_uses_energy_when_no_motion_score():
    """Falls scene nur 'energy' hat (Legacy-Schema) → als motion_score nutzen."""
    class _Legacy:
        id = 7
        energy = 0.6
        ai_mood = "calm"
    cf = build_clip_features(video_clip_id=1, scene=_Legacy())
    assert cf.motion_score == 0.6
