"""Brain V3 — Smart-Sampler (Phase 4, 06_PHASES.md Z.323-324).

Liefert Top-N Cuts nach Bayes-Varianz fuer Lern-Sessions.

Bayes-Varianz Beta(α, β):
    var = α·β / ((α+β)² · (α+β+1))

Hohe Varianz = hohe Unsicherheit = lohnt sich zu lernen.

Verwendung:
- Diese Funktion liefert top-N axis_weights-Buckets, sortiert nach Varianz
  (absteigend). Caller bekommt damit die unsichersten Lern-Punkte.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from services.brain.weight_store import WeightStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SamplePoint:
    axis: str
    context_level: int
    context_key: str
    alpha: float
    beta: float
    variance: float
    posterior_mean: float


def _beta_variance(alpha: float, beta: float) -> float:
    """Bayes-Varianz fuer Beta(α, β). Numerisch stabil mit +1e-9."""
    n = alpha + beta
    denom = (n ** 2) * (n + 1) + 1e-9
    return (alpha * beta) / denom


def _posterior_mean(alpha: float, beta: float) -> float:
    return (alpha + 1.0) / (alpha + beta + 2.0)


def sample_uncertain(
    weight_store: WeightStore,
    n: int = 15,
    min_samples: float = 1.0,
) -> list[SamplePoint]:
    """Liefert Top-N axis_weights-Eintraege nach Bayes-Varianz absteigend.

    Args:
        weight_store: aktiver WeightStore (offene weights.db)
        n: wie viele Top-Punkte zurueckgeben
        min_samples: skip Buckets mit α+β < min_samples (default 1.0 →
                     Buckets brauchen >=1 Beobachtung damit Varianz aussagt)

    Returns:
        Liste mit max. n Eintraegen, sortiert nach `variance` desc.
    """
    if n <= 0:
        return []
    conn = weight_store._get_conn()  # noqa: SLF001 (intern, single-thread)
    rows = conn.execute(
        "SELECT axis, context_level, context_key, "
        "positive_count, negative_count "
        "FROM axis_weights "
        "WHERE (positive_count + negative_count) >= ?",
        (float(min_samples),),
    ).fetchall()
    points: list[SamplePoint] = []
    for axis, lvl, key, alpha, beta in rows:
        a = float(alpha or 0.0)
        b = float(beta or 0.0)
        points.append(SamplePoint(
            axis=axis, context_level=int(lvl), context_key=key,
            alpha=a, beta=b,
            variance=_beta_variance(a, b),
            posterior_mean=_posterior_mean(a, b),
        ))
    points.sort(key=lambda p: p.variance, reverse=True)
    return points[:n]
