"""Brain V3 — BridgeDimensions (Plan-Doc 05).

Berechnet pro Cut + Kandidat 17 normalisierte Bridge-Werte (0..1).

Phase 3: simplified Implementation. Audio-Achsen kommen aus
TriggerSettings-ähnlichen Roh-Features. Video-Achsen aus Visual-Curves
+ Embedding-Cosine-Similarity.

Ein-Wert-pro-Achse-API: `compute(axis, candidate, cut_context) -> float in [0, 1]`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from services.brain.cold_start import BRIDGE_AXES
from services.brain.context_resolver import CutContext

logger = logging.getLogger(__name__)


@dataclass
class ClipCandidate:
    """Mini-View auf einen Video-Clip-Kandidaten für Bridge-Bewertung."""
    clip_id: str
    duration_s: float
    motion_score: float = 0.5
    brightness: float = 0.5
    saturation: float = 0.5
    color_temp: float = 0.0  # -1..+1
    embedding: Optional[np.ndarray] = None  # 768-dim SigLIP-2
    mood_tags: list[str] = field(default_factory=list)
    style_tags: list[str] = field(default_factory=list)


def _clip01(x: float) -> float:
    """Clip auf [0, 1]."""
    return max(0.0, min(1.0, float(x)))


class BridgeDimensions:
    """Stateless-Calculator. Eine Instanz pro Reranker-Lifecycle reicht."""

    def compute(
        self,
        axis: str,
        candidate: ClipCandidate,
        cut_context: CutContext,
    ) -> float:
        """Liefert einen Wert in [0, 1] für (axis, candidate, context)."""
        if axis not in BRIDGE_AXES:
            raise ValueError(f"Unbekannte Achse: {axis!r}")
        method = getattr(self, f"_compute_{axis}", None)
        if method is None:
            # Fallback: 0.5 — Plan-Doc 05 Cold-Start-Mitte
            return 0.5
        try:
            return _clip01(method(candidate, cut_context))
        except Exception:
            # F-21 (B-353): keep the 0.5 neutral fallback so one broken axis does
            # not crash the whole scoring pass, but log with traceback at error
            # level so a systematically failing axis is visible instead of silent.
            logger.exception(
                "BridgeDimensions.compute(%s) failed — neutral 0.5 fallback", axis)
            return 0.5

    def compute_all(
        self,
        candidate: ClipCandidate,
        cut_context: CutContext,
    ) -> dict[str, float]:
        """Liefert alle 17 Achsen-Werte als dict."""
        return {ax: self.compute(ax, candidate, cut_context) for ax in BRIDGE_AXES}

    # ------------------------------------------------------------------
    # 10 Audio-Achsen — basieren auf raw_audio_features im CutContext
    # ------------------------------------------------------------------
    def _compute_beat_weight(self, c: ClipCandidate, ctx: CutContext) -> float:
        return float(ctx.raw_audio_features.get("beat_strength", 0.5))

    def _compute_onset_weight(self, c: ClipCandidate, ctx: CutContext) -> float:
        return float(ctx.raw_audio_features.get("onset_strength", 0.5))

    def _compute_kick_weight(self, c: ClipCandidate, ctx: CutContext) -> float:
        return float(ctx.raw_audio_features.get("kick_present", 0.5))

    def _compute_snare_weight(self, c: ClipCandidate, ctx: CutContext) -> float:
        return float(ctx.raw_audio_features.get("snare_present", 0.5))

    def _compute_hihat_weight(self, c: ClipCandidate, ctx: CutContext) -> float:
        return float(ctx.raw_audio_features.get("hihat_present", 0.5))

    def _compute_energy_weight(self, c: ClipCandidate, ctx: CutContext) -> float:
        return float(ctx.raw_audio_features.get("energy", 0.5))

    def _compute_energy_threshold(self, c: ClipCandidate, ctx: CutContext) -> float:
        return float(ctx.raw_audio_features.get("energy", 0.5))

    def _compute_onset_sensitivity(self, c: ClipCandidate, ctx: CutContext) -> float:
        return float(ctx.raw_audio_features.get("onset_sensitivity", 0.5))

    def _compute_min_clip_length(self, c: ClipCandidate, ctx: CutContext) -> float:
        # Kürzere Clips = höherer Wert wenn min-Länge wichtig ist
        # Heuristik: 1 - normalize(duration_s, 0.5, 8.0)
        d = c.duration_s
        return 1.0 - _clip01((d - 0.5) / 7.5)

    def _compute_max_clip_length(self, c: ClipCandidate, ctx: CutContext) -> float:
        d = c.duration_s
        return _clip01((d - 0.5) / 7.5)

    # ------------------------------------------------------------------
    # 7 Video-Achsen
    # ------------------------------------------------------------------
    def _compute_motion_match_weight(self, c: ClipCandidate, ctx: CutContext) -> float:
        # Pearson-ähnlich: motion_score vs. audio_energy
        target = float(ctx.raw_audio_features.get("energy", 0.5))
        return 1.0 - abs(c.motion_score - target)

    def _compute_scene_cut_weight(self, c: ClipCandidate, ctx: CutContext) -> float:
        # Phasen-Distanz zum Beat — heuristisch via raw_audio_features
        return float(ctx.raw_audio_features.get("on_beat", 0.5))

    def _compute_brightness_match_weight(self, c: ClipCandidate, ctx: CutContext) -> float:
        target = float(ctx.raw_audio_features.get("spectral_centroid_norm", 0.5))
        return 1.0 - abs(c.brightness - target)

    def _compute_color_temp_match_weight(self, c: ClipCandidate, ctx: CutContext) -> float:
        # Mood mapping: dark → kalt, uplifting → warm, neutral → 0
        mood_map = {"dark": -0.5, "neutral": 0.0, "uplifting": 0.5}
        target = mood_map.get(ctx.audio_mood, 0.0)
        # color_temp -1..+1, target -1..+1, distance auf 0..2 normalisiert
        return 1.0 - abs(c.color_temp - target) / 2.0

    def _compute_pace_match_weight(self, c: ClipCandidate, ctx: CutContext) -> float:
        # Shot-Länge vs. BPM-Gefühl
        bpm_target = {"slow": 0.3, "medium": 0.6, "fast": 0.9}.get(
            ctx.video_pace_class, 0.5)
        # Kurze Clips = schneller pace
        clip_pace = 1.0 - _clip01((c.duration_s - 0.5) / 7.5)
        return 1.0 - abs(clip_pace - bpm_target)

    def _compute_semantic_match_weight(self, c: ClipCandidate, ctx: CutContext) -> float:
        # Cosine-Similarity SigLIP-2-Embedding vs Audio-Mood-Prototyp
        # Vereinfacht: ohne Audio-Embedding-Prototyp gibt 0.5 zurück
        if c.embedding is None:
            return 0.5
        prototype = ctx.raw_audio_features.get("mood_prototype")
        if prototype is None:
            return 0.5
        proto = np.asarray(prototype, dtype="float32")
        if proto.shape != c.embedding.shape:
            return 0.5
        norm_a = float(np.linalg.norm(c.embedding)) + 1e-9
        norm_b = float(np.linalg.norm(proto)) + 1e-9
        cos = float(np.dot(c.embedding, proto) / (norm_a * norm_b))
        return (cos + 1.0) / 2.0  # -1..+1 → 0..1

    def _compute_mood_match_weight(self, c: ClipCandidate, ctx: CutContext) -> float:
        # Tag-Overlap: video.mood_tags ∩ {ctx.audio_mood}
        return 1.0 if ctx.audio_mood in c.mood_tags else 0.0
