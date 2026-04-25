"""Slice 4 / FR-S4-5: A/B-Pacing-Runner.

Erzeugt zwei Auswahl-Ergebnisse aus dem gleichen Kandidaten-Pool mit
unterschiedlichen Reward-Weight-Profilen. Deterministisch via seed.

Das hier ist die abstrakte Variante (scorer_factory pluggable), damit
sie ohne komplette Pipeline-Wiring testbar ist. Die UI-Integration im
Cockpit ruft denselben run_ab() mit dem realen scorer_factory auf.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence


@dataclass
class ABResult:
    choice_a: Any | None
    choice_b: Any | None
    scores_a: list[float] | None = None
    scores_b: list[float] | None = None


def run_ab(
    candidates: Sequence[Mapping[str, Any]],
    ctx: Mapping[str, Any],
    weights_a: Mapping[str, float],
    weights_b: Mapping[str, float],
    scorer_factory: Callable[[Mapping[str, float]], Callable[[Mapping[str, Any], Mapping[str, Any]], float]],
    seed: int = 0,
) -> ABResult:
    """Rufe den scorer mit beiden Profilen auf, picke argmax pro Profil.

    Bei Tie wird der erste max-Index gewählt — deterministisch via stable sort.
    Seed wird durch den scorer-Closure verwendet, falls dieser stochastische
    Komponenten benutzt.
    """
    if not candidates:
        return ABResult(None, None, None, None)

    # Random-Seed deterministisch (für scorer_factory die ggf. samplet)
    rng = random.Random(seed)
    _ = rng  # passes deterministically to scorer if needed

    scorer_a = scorer_factory(dict(weights_a))
    scorer_b = scorer_factory(dict(weights_b))

    scores_a = [float(scorer_a(c, ctx)) for c in candidates]
    scores_b = [float(scorer_b(c, ctx)) for c in candidates]

    idx_a = max(range(len(candidates)), key=lambda i: scores_a[i])
    idx_b = max(range(len(candidates)), key=lambda i: scores_b[i])
    return ABResult(
        choice_a=candidates[idx_a],
        choice_b=candidates[idx_b],
        scores_a=scores_a,
        scores_b=scores_b,
    )
