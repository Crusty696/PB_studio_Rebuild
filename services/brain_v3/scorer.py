"""Brain V3 — Scorer (Plan-Doc 05).

Kombiniert Bridge-Werte (BridgeDimensions) mit gelernten Gewichten
(WeightStore.get_posterior_mean) → Final-Score pro Kandidat plus
17 Sub-Scores für UI-Diagnostik.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from services.brain_v3.bridge_dimensions import BridgeDimensions, ClipCandidate
from services.brain_v3.cold_start import BRIDGE_AXES
from services.brain_v3.context_resolver import CutContext, context_keys
from services.brain_v3.weight_store import WeightStore


@dataclass
class ScoredCandidate:
    candidate: ClipCandidate
    final_score: float
    brain_v3_scores: dict[str, float] = field(default_factory=dict)


class Scorer:
    """Stateless-Scorer. Eine Instanz pro Reranker-Lifecycle."""

    def __init__(self, bridge: BridgeDimensions, weights: WeightStore):
        self.bridge = bridge
        self.weights = weights

    def score(
        self,
        candidate: ClipCandidate,
        cut_context: CutContext,
    ) -> ScoredCandidate:
        keys = context_keys(cut_context)
        sub_scores: dict[str, float] = {}
        for axis in BRIDGE_AXES:
            bridge_value = self.bridge.compute(axis, candidate, cut_context)
            weight = self.weights.get_posterior_mean(axis, keys)
            sub_scores[axis] = bridge_value * weight
        # Final = Mittel aller 17 gewichteten Sub-Scores
        final = sum(sub_scores.values()) / len(sub_scores)
        return ScoredCandidate(
            candidate=candidate,
            final_score=final,
            brain_v3_scores=sub_scores,
        )

    def score_all(
        self,
        candidates: list[ClipCandidate],
        cut_context: CutContext,
    ) -> list[ScoredCandidate]:
        """Bewertet alle Kandidaten + sortiert absteigend nach final_score."""
        scored = [self.score(c, cut_context) for c in candidates]
        scored.sort(key=lambda s: s.final_score, reverse=True)
        return scored
