"""Slice 4 / FR-S4-4: Pacing-Decision-Explainer (Logik-Layer).

Headless-Logik: liefert die Top-N Reward-Komponenten und Penalties für
einen einzelnen Decision-Record. UI-Widget (`ui/widgets/pacing_decision_
explorer.py`) konsumiert diese Funktion.
"""
from __future__ import annotations

from typing import Any, Mapping

from services.pacing.rl_reward import REWARD_KEYS, RewardComponents, compute_reward


def explain_decision(
    components: RewardComponents,
    weights: Mapping[str, float] | None = None,
    user_verdict: str | None = None,
    top_n: int = 3,
) -> dict[str, Any]:
    """Liefert Top-N Komponenten + total + breakdown.

    Returns:
        {
          "total_reward": float,
          "user_verdict": str | None,
          "top_components": [{"key": str, "value": float, "weight": float, "contribution": float}],
          "breakdown": {key: contribution}  (alle 7 Keys),
        }
    """
    from services.pacing.rl_reward import DEFAULT_WEIGHTS
    w = dict(DEFAULT_WEIGHTS)
    if weights is not None:
        for k, v in weights.items():
            if k in REWARD_KEYS:
                w[k] = float(v)
    total_w = sum(w.values()) or 1.0

    comps = components.as_dict()
    if user_verdict == "good":
        comps["r_user"] = 1.0
    elif user_verdict == "bad":
        comps["r_user"] = 0.0

    contribs = {k: (w[k] / total_w) * comps[k] for k in REWARD_KEYS}
    sorted_keys = sorted(REWARD_KEYS, key=lambda k: contribs[k], reverse=True)
    top = [
        {"key": k, "value": float(comps[k]), "weight": float(w[k] / total_w), "contribution": float(contribs[k])}
        for k in sorted_keys[: max(1, int(top_n))]
    ]
    return {
        "total_reward": compute_reward(components, user_verdict=user_verdict, weights=weights),
        "user_verdict": user_verdict,
        "top_components": top,
        "breakdown": {k: float(contribs[k]) for k in REWARD_KEYS},
    }
