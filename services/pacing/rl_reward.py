"""Slice 4 / FR-S4-1: RL-Reward-Function (7 gewichtete Komponenten).

Komponenten:
- r_energy:      Audio-RMS ↔ Video-Motion (FR-S1-4)
- r_mood:        Audio-Mood-Vec ↔ Clip-Caption-Emb (FR-S3-2)
- r_stem_class:  Stem-dominante Section ↔ Shot-Type (FR-S2-2)
- r_section:     Section-Coherence (FR-S3-4)
- r_freshness:   1 - variety_memory.penalty (FR-S3-3)
- r_collision:   1 - collision_penalty (Existing scorer.collision_penalty)
- r_user:        Hard-Override durch User-Verdict (Truth-Set)
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Mapping

REWARD_KEYS: tuple[str, ...] = (
    "r_energy",
    "r_mood",
    "r_stem_class",
    "r_section",
    "r_freshness",
    "r_collision",
    "r_user",
)

DEFAULT_WEIGHTS: dict[str, float] = {k: 1.0 / len(REWARD_KEYS) for k in REWARD_KEYS}


@dataclass(frozen=True)
class RewardComponents:
    r_energy: float
    r_mood: float
    r_stem_class: float
    r_section: float
    r_freshness: float
    r_collision: float
    r_user: float

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


def _validate(value: float, key: str) -> None:
    if not (0.0 <= value <= 1.0):
        raise ValueError(f"{key} must be in [0, 1], got {value}")


def compute_reward(
    components: RewardComponents,
    user_verdict: str | None = None,
    weights: Mapping[str, float] | None = None,
) -> float:
    """Gewichtete Summe der 7 Komponenten ∈ [0, 1].

    Args:
        components: alle 7 Sub-Reward-Werte ∈ [0, 1].
        user_verdict: 'good' / 'bad' / None. Override für r_user.
            'good' → r_user = 1.0; 'bad' → r_user = 0.0; sonst → r_user unverändert.
        weights: Override-Map. Müssen REWARD_KEYS sein. Werden auf Σ=1 normalisiert.

    Returns:
        Total-Reward ∈ [0, 1].
    """
    comps = components.as_dict()
    for k, v in comps.items():
        _validate(v, k)

    # User-Verdict-Override
    if user_verdict == "good":
        comps["r_user"] = 1.0
    elif user_verdict == "bad":
        comps["r_user"] = 0.0
    # andere → unverändert

    # Weights
    w = dict(DEFAULT_WEIGHTS)
    if weights is not None:
        unknown = set(weights.keys()) - set(REWARD_KEYS)
        if unknown:
            raise ValueError(f"Unknown weight keys: {sorted(unknown)}")
        # Override
        for k, v in weights.items():
            w[k] = float(v)
        # Komponenten ohne explizites Gewicht auf 0 setzen
        for k in REWARD_KEYS:
            if k not in weights:
                w[k] = 0.0

    total_w = sum(w.values())
    if total_w <= 0:
        return 0.0

    # Σ(weight_i * comp_i) / Σ(weight_i)
    return float(sum(w[k] * comps[k] for k in REWARD_KEYS) / total_w)
