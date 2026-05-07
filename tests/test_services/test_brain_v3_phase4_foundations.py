"""Tests fuer Phase 4 Foundations: quantize_quartile, context_mapping, schemas."""
from __future__ import annotations

import pytest

from services.brain_v3.context_resolver import (
    quantize_quartile,
    quantize_tertile,
    CutContext,
)
from services.brain_v3.context_mapping import (
    ContextMappingConfig,
    DEFAULT_SECTION_MAP,
    DEFAULT_MOOD_MAP,
    map_section,
    map_mood,
    derive_pace_class,
    build_cut_context,
)
from services.brain_v3.schemas.brain_v3_schemas import (
    SuggestRequest,
    SuggestResponse,
    FeedbackRequest,
    FeedbackResponse,
    StatsResponse,
    ResetRequest,
)


# ---------------- quantize_quartile ----------------------------------------
def test_quantize_quartile_lowest():
    assert quantize_quartile(0.1, p25=0.25, p50=0.5, p75=0.75) == "low"


def test_quantize_quartile_low_mid():
    assert quantize_quartile(0.3, p25=0.25, p50=0.5, p75=0.75) == "medium"


def test_quantize_quartile_high_mid():
    assert quantize_quartile(0.6, p25=0.25, p50=0.5, p75=0.75) == "high"


def test_quantize_quartile_extreme():
    assert quantize_quartile(0.95, p25=0.25, p50=0.5, p75=0.75) == "extreme"


def test_quantize_quartile_custom_classes():
    cls = ("a", "b", "c", "d")
    assert quantize_quartile(0.0, 0.25, 0.5, 0.75, classes=cls) == "a"
    assert quantize_quartile(1.0, 0.25, 0.5, 0.75, classes=cls) == "d"


# ---------------- ContextMappingConfig -------------------------------------
def test_default_mapping_config_valid():
    cfg = ContextMappingConfig()
    assert cfg.pace_source == "recent_cuts"
    assert "chorus" in cfg.section_map
    assert cfg.section_map["chorus"] == "drop"
    assert cfg.mood_map["calm"] == "neutral"


def test_invalid_section_target_raises():
    with pytest.raises(ValueError, match="VALID_SECTIONS"):
        ContextMappingConfig(section_map={"foo": "bogus"})


def test_invalid_mood_target_raises():
    with pytest.raises(ValueError, match="VALID_MOOD"):
        ContextMappingConfig(mood_map={"foo": "joyful"})


def test_invalid_pace_source_raises():
    with pytest.raises(ValueError, match="pace_source"):
        ContextMappingConfig(pace_source="invented")


def test_map_section_uses_default():
    cfg = ContextMappingConfig()
    assert map_section("chorus", cfg) == "drop"
    assert map_section("bridge", cfg) == "transition"
    assert map_section("UNKNOWN_X", cfg) == "verse"  # fallback


def test_map_mood_uses_default():
    cfg = ContextMappingConfig()
    assert map_mood("calm", cfg) == "neutral"
    assert map_mood("dramatic", cfg) == "dark"
    assert map_mood("foo_unknown", cfg) == "neutral"


def test_derive_pace_class_recent_cuts():
    cfg = ContextMappingConfig(pace_source="recent_cuts")
    assert derive_pace_class(cfg, recent_cut_count=1) == "slow"
    assert derive_pace_class(cfg, recent_cut_count=4) == "medium"
    assert derive_pace_class(cfg, recent_cut_count=10) == "fast"
    assert derive_pace_class(cfg, recent_cut_count=None) == "medium"


def test_derive_pace_class_audio_bpm():
    cfg = ContextMappingConfig(pace_source="audio_bpm")
    assert derive_pace_class(cfg, audio_bpm=80) == "slow"
    assert derive_pace_class(cfg, audio_bpm=120) == "medium"
    assert derive_pace_class(cfg, audio_bpm=160) == "fast"
    assert derive_pace_class(cfg, audio_bpm=None) == "medium"


def test_derive_pace_class_fixed_medium():
    cfg = ContextMappingConfig(pace_source="fixed_medium")
    assert derive_pace_class(cfg, recent_cut_count=99, audio_bpm=999) == "medium"


# ---------------- build_cut_context ----------------------------------------
def test_build_cut_context_returns_valid_cutcontext():
    cfg = ContextMappingConfig()
    ctx = build_cut_context(
        raw_section="chorus",
        raw_mood="dramatic",
        raw_subtrack_position="middle",
        raw_energy_level="high",
        raw_motion_class="extreme",
        cfg=cfg,
        recent_cut_count=8,
        audio_bpm=140,
    )
    assert isinstance(ctx, CutContext)
    assert ctx.audio_section_type == "drop"
    assert ctx.audio_mood == "dark"
    assert ctx.audio_energy_level == "high"
    assert ctx.video_motion_class == "extreme"
    assert ctx.video_pace_class == "fast"  # recent_cut_count > 5


def test_build_cut_context_passes_raw_features():
    cfg = ContextMappingConfig()
    audio_feats = {"bpm": 128.5, "key": "Am"}
    video_feats = {"motion_score": 0.42}
    ctx = build_cut_context(
        raw_section="verse", raw_mood="neutral",
        raw_subtrack_position="start", raw_energy_level="low",
        raw_motion_class="low",
        cfg=cfg,
        raw_audio_features=audio_feats,
        raw_video_features=video_feats,
    )
    assert ctx.raw_audio_features == audio_feats
    assert ctx.raw_video_features == video_feats


# ---------------- Schemas --------------------------------------------------
def test_suggest_request_defaults():
    req = SuggestRequest(audio_clip_id=1, video_clip_ids=[1, 2, 3])
    assert req.n_top == 5
    assert req.use_brain_v3 is True
    assert req.min_confidence == 0.0


def test_feedback_request_validates_rating():
    req = FeedbackRequest(cut_id=42, rating="perfect")
    assert req.rating == "perfect"
    with pytest.raises(Exception):
        FeedbackRequest(cut_id=42, rating="invalid_rating")


def test_stats_response_axis_bounds():
    s = StatsResponse(total_clicks=10, cold_start_axes=5, learned_axes=12)
    assert 0 <= s.cold_start_axes <= 17
    assert 0 <= s.learned_axes <= 17
    with pytest.raises(Exception):
        StatsResponse(total_clicks=0, cold_start_axes=20, learned_axes=0)


def test_reset_request_optional_token():
    r1 = ResetRequest()
    assert r1.confirmation_token is None
    r2 = ResetRequest(confirmation_token="abc123")
    assert r2.confirmation_token == "abc123"
