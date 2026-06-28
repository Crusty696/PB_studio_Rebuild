"""Brain V3 — Reranker (Phase 4, Plan-Doc 06 Z.317-323).

Eingriff in `services.pacing.pipeline.PacingPipeline.select_best()` Stage 4:
- Input: `scored`-Liste aus Pacing-Pipeline (passed_stage2 == True)
- Brain-V3-Reranker bewertet jeden Kandidaten ueber 17 Achsen x 6 Levels
- Output: re-sortierte Liste + `brain_v3_scores` pro Kandidat

Stages 1-3 (Hard-Rules, Variations-Budget, Collision-Check) bleiben
unangetastet — der Reranker ersetzt nur die Stage-4-Sortierung.

Blend mit Original-Soft-Score:
    final = brain_score * brain_weight + pacing_soft_score * (1 - brain_weight)
brain_weight = 1.0 (default) → reine Brain-V3-Sortierung
brain_weight = 0.0 → kein Reranking (aequivalent zu disabled)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional, Sequence

import numpy as np

from services.brain.bridge_dimensions import BridgeDimensions, ClipCandidate
from services.brain.context_mapping import ContextMappingConfig, build_cut_context
from services.brain.context_resolver import (
    CutContext,
    quantize_tertile,
)
from services.brain.scorer import Scorer
from services.brain.weight_store import WeightStore

logger = logging.getLogger(__name__)


@dataclass
class RerankedCandidate:
    """Ergebnis pro Kandidat: original + brain-final + sub-scores."""
    clip_id: int
    original_soft_score: float
    brain_score: float
    final_score: float
    brain_v3_scores: dict[str, float]


class BrainV3Reranker:
    """Stateless-Reranker. Eine Instanz pro Pacing-Run (oder Singleton)."""

    def __init__(
        self,
        weight_store: WeightStore,
        bridge: Optional[BridgeDimensions] = None,
        mapping_config: Optional[ContextMappingConfig] = None,
        brain_weight: float = 1.0,
        min_confidence: float = 0.0,
    ):
        self._weights = weight_store
        self._bridge = bridge or BridgeDimensions()
        self._scorer = Scorer(self._bridge, self._weights)
        self._mapping = mapping_config or ContextMappingConfig()
        if not 0.0 <= brain_weight <= 1.0:
            raise ValueError(f"brain_weight muss in [0,1] sein, war {brain_weight}")
        self._brain_weight = float(brain_weight)
        self._min_confidence = float(min_confidence)

    # ------------------------------------------------------------------
    # Hauptmethode: bekommt das Pacing-Stage-4-Output, gibt re-sortiert zurueck
    # ------------------------------------------------------------------
    def rerank(
        self,
        scored: Sequence[tuple[Any, float, dict[str, float]]],
        ctx: Any,
        recent_clip_ids: Optional[Sequence[int]] = None,
    ) -> list[RerankedCandidate]:
        """Rerank stage-4 candidates.

        Args:
            scored: Liste von (ClipFeatures-aehnlich, soft_score, contribs)
                aus PacingPipeline. ClipFeatures muss `clip_id`,
                `motion_score`, optional `embedding` exposen.
            ctx: AudioContext aus PacingPipeline (with `at_section_type`,
                `at_mood_audio`, `at_bpm`, ...).
            recent_clip_ids: optionale Liste der letzten gewaehlten Clips
                (fuer pace_class derive_pace_class).

        Returns:
            Liste `RerankedCandidate`, sortiert absteigend nach `final_score`.
        """
        cut_context = self._build_cut_context_from_audio(ctx, recent_clip_ids)
        results: list[RerankedCandidate] = []
        for clip_feat, soft_score, contribs in scored:
            candidate = self._adapt_clip(clip_feat, contribs)
            scored_brain = self._scorer.score(candidate, cut_context)
            blended = (
                self._brain_weight * scored_brain.final_score
                + (1.0 - self._brain_weight) * float(soft_score or 0.0)
            )
            if blended < self._min_confidence:
                continue
            results.append(RerankedCandidate(
                clip_id=int(getattr(clip_feat, "clip_id", -1)),
                original_soft_score=float(soft_score or 0.0),
                brain_score=float(scored_brain.final_score),
                final_score=blended,
                brain_v3_scores=dict(scored_brain.brain_v3_scores),
            ))
        results.sort(key=lambda r: r.final_score, reverse=True)
        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _build_cut_context_from_audio(
        self,
        ctx: Any,
        recent_clip_ids: Optional[Sequence[int]],
    ) -> CutContext:
        recent_cut_count = len(recent_clip_ids) if recent_clip_ids else 0
        raw_section = (getattr(ctx, "at_section_type", None) or "verse")
        raw_mood = (getattr(ctx, "at_mood_audio", None) or "neutral")
        raw_bpm = getattr(ctx, "at_bpm", None)
        raw_energy = getattr(ctx, "at_energy", None)
        # Energy-Quantize: tertile auf [0..1]
        if raw_energy is None:
            energy_class = "medium"
        else:
            energy_class = quantize_tertile(float(raw_energy), p33=0.33, p66=0.66)
        # Audio-Subtrack-Position: ohne Subtrack-Info → middle
        subpos = "middle"
        # Motion-Klasse: kommt vom Reranker erst beim Per-Candidate-Scoring;
        # fuer den Backoff-Key aber nur grob: median Motion = "medium".
        motion_class = "medium"
        return build_cut_context(
            raw_section=raw_section,
            raw_mood=raw_mood,
            raw_subtrack_position=subpos,
            raw_energy_level=energy_class,
            raw_motion_class=motion_class,
            cfg=self._mapping,
            recent_cut_count=recent_cut_count,
            audio_bpm=raw_bpm,
            raw_audio_features={
                "energy": float(raw_energy) if raw_energy is not None else 0.5,
                "bpm": float(raw_bpm) if raw_bpm else 120.0,
                "section_type": raw_section,
                "mood": raw_mood,
                "harmonic_tension": float(getattr(ctx, "at_harmonic_tension", None) or 0.0),
            },
        )

    @staticmethod
    def _adapt_clip(clip_feat: Any, contribs: dict[str, float]) -> ClipCandidate:
        """Adapter PacingPipeline.ClipFeatures → brain_v3.ClipCandidate."""
        emb = getattr(clip_feat, "embedding", None)
        emb_arr: Optional[np.ndarray] = None
        if emb is not None:
            try:
                emb_arr = np.asarray(emb, dtype=np.float32)
            except Exception:
                emb_arr = None
        return ClipCandidate(
            clip_id=str(getattr(clip_feat, "clip_id", "?")),
            duration_s=float(contribs.get("duration_s", 1.0) or 1.0),
            motion_score=float(getattr(clip_feat, "motion_score", 0.5) or 0.5),
            brightness=float(contribs.get("brightness", 0.5) or 0.5),
            saturation=float(contribs.get("saturation", 0.5) or 0.5),
            color_temp=float(contribs.get("color_temp", 0.0) or 0.0),
            embedding=emb_arr,
            mood_tags=list(contribs.get("mood_tags", []) or []),
            style_tags=list(contribs.get("style_tags", []) or []),
        )
