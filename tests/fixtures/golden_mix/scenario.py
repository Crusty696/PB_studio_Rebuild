"""Deterministic scenario builder for the Golden-Run-Snapshot test (P14).

This module is the single source of truth for the inputs used by both
`scripts/generate_golden_decisions.py` (regenerates the baseline) and
`tests/integration/test_golden_run_snapshot.py` (asserts no drift).

The scenario intentionally avoids touching the real golden_mix audio fixture
(`segment.wav`) or the 20 MP4 clips — those assets are multi-megabyte and
loading them through the full audio-analysis pipeline would be slow and
non-deterministic on CI (beat-detection jitter, FFmpeg decode variance).
Instead, we build 20 synthetic ClipFeatures seeded deterministically and
feed them through `PacingPipeline.select_best()` for a fixed sequence of 10
AudioContext cut-points simulating a mix progression.

The golden_mix fixture directory on disk is kept as a provenance artefact
(audio source file + provenance JSON + selection report), so the link
between this synthetic snapshot and the real golden mix is documented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from services.pacing.scorer import AudioContext, ClipFeatures

__all__ = [
    "GoldenScenario",
    "build_golden_scenario",
    "CLIP_COUNT",
    "CUT_COUNT",
    "EMBEDDING_DIM",
]

# ── Scenario knobs (change = baseline drift; regenerate on purpose) ────────
CLIP_COUNT: int = 20
CUT_COUNT: int = 10
EMBEDDING_DIM: int = 8  # small dims → fast + stable FP; we only care about cos-sim

# Fixed 10-cut section progression. Names match config/pacing_rules.yaml keys.
_SECTIONS: tuple[str, ...] = (
    "intro",
    "buildup",
    "drop",
    "buildup",
    "drop",
    "breakdown",
    "buildup",
    "drop",
    "outro",
    "outro",
)

# Per-cut timestamps at 30s intervals starting at 0s.
_CUT_INTERVAL_SEC: float = 30.0

# Roles rotated across 20 clips. Must cover what sections demand
# (hero/action for drop, establishing/ambient/detail for intro/outro, etc.).
_ROLES: tuple[str, ...] = (
    "hero",
    "action",
    "transition",
    "detail",
    "establishing",
    "filler",
    "hero",
    "action",
    "transition",
    "detail",
    "hero",
    "ambient",
    "hero",
    "detail",
    "action",
    "establishing",
    "hero",
    "transition",
    "detail",
    "ambient",
)

# Moods rotated across 20 clips — 4 distinct refined labels.
_MOODS: tuple[str, ...] = (
    "euphoric",
    "calm",
    "energetic",
    "melancholic",
) * 5

# Style bucket ids rotated across 20 clips (buckets 1..5).
_STYLE_BUCKETS: tuple[int, ...] = tuple((i % 5) + 1 for i in range(CLIP_COUNT))

# Motion scores — varied but deterministic (no RNG; encoded table).
_MOTION_SCORES: tuple[float, ...] = (
    0.90, 0.75, 0.55, 0.30, 0.15,
    0.85, 0.70, 0.50, 0.35, 0.20,
    0.80, 0.65, 0.45, 0.25, 0.60,
    0.40, 0.95, 0.10, 0.50, 0.05,
)


@dataclass(frozen=True)
class GoldenScenario:
    """Immutable inputs for the golden run.

    Keep frozen so callers can't accidentally mutate the shared fixture
    between the baseline-regeneration script and the test.
    """

    candidates: Sequence[ClipFeatures]
    cuts: Sequence[AudioContext]
    weights_profile: str = "default"
    meta: dict[str, object] = field(default_factory=dict)


def _make_clip(clip_id: int) -> ClipFeatures:
    """Build one deterministic ClipFeatures.

    Embedding: np.random.default_rng(42 + clip_id).standard_normal(EMBEDDING_DIM).
    Scene id: clip_id * 10 (matches the pattern used elsewhere in the test suite).
    """
    rng = np.random.default_rng(42 + clip_id)
    embedding = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
    return ClipFeatures(
        clip_id=clip_id,
        scene_id=clip_id * 10,
        role=_ROLES[clip_id - 1],
        mood_refined=_MOODS[clip_id - 1],
        style_bucket_id=_STYLE_BUCKETS[clip_id - 1],
        motion_score=_MOTION_SCORES[clip_id - 1],
        embedding=embedding,
    )


def _make_cut(sequence_idx: int) -> AudioContext:
    """Build one deterministic AudioContext for cut #sequence_idx (0-based)."""
    section = _SECTIONS[sequence_idx]
    ts = sequence_idx * _CUT_INTERVAL_SEC

    # Section-shaped audio features. Energies and tensions follow the mix
    # shape — drops peak, breakdowns dip, intro/outro are moderate.
    section_profiles: dict[str, dict[str, Any]] = {
        "intro":      {"energy": 0.35, "tension": 0.25, "mood": "calm",       "bpm": 138.0, "key": "Am"},
        "buildup":    {"energy": 0.65, "tension": 0.60, "mood": "energetic",  "bpm": 140.0, "key": "Am"},
        "drop":       {"energy": 0.90, "tension": 0.80, "mood": "energetic",  "bpm": 140.0, "key": "Am"},
        "breakdown":  {"energy": 0.40, "tension": 0.35, "mood": "calm",       "bpm": 140.0, "key": "Em"},
        "outro":      {"energy": 0.25, "tension": 0.15, "mood": "calm",       "bpm": 136.0, "key": "Em"},
    }
    prof = section_profiles[section]

    return AudioContext(
        at_timestamp_sec=ts,
        at_beat_idx=int(ts * (float(prof["bpm"]) / 60.0)),  # beats since t=0
        at_section_type=section,
        at_bpm=float(prof["bpm"]),
        at_energy=float(prof["energy"]),
        at_key=str(prof["key"]),
        at_key_confidence=0.85,
        at_harmonic_tension=float(prof["tension"]),
        at_mood_audio=str(prof["mood"]),
        at_mood_video=str(prof["mood"]),
        at_genre="psytrance",
        at_sub_genre="progressive_psy",
        at_spectral_hash=f"hash_{section}",
        at_groove_template="fotf",
        at_lufs=-8.5,
    )


def build_golden_scenario() -> GoldenScenario:
    """Deterministic inputs for the golden-run snapshot.

    Scene-ids: 10..200 (step 10). Roles: mix of hero/filler/transition/detail.
    Moods: euphoric/melancholic/calm/energetic (4 distinct labels).
    Style bucket ids: 1..5.
    AudioContexts: 10 cuts at 30s intervals, section progression
      ['intro', 'buildup', 'drop', 'buildup', 'drop', 'breakdown', 'buildup',
       'drop', 'outro', 'outro'].
    """
    candidates = tuple(_make_clip(i) for i in range(1, CLIP_COUNT + 1))
    cuts = tuple(_make_cut(i) for i in range(CUT_COUNT))
    return GoldenScenario(
        candidates=candidates,
        cuts=cuts,
        weights_profile="default",
        meta={
            "clip_count": CLIP_COUNT,
            "cut_count": CUT_COUNT,
            "embedding_dim": EMBEDDING_DIM,
            "embedding_seed_base": 42,
            "cut_interval_sec": _CUT_INTERVAL_SEC,
        },
    )
