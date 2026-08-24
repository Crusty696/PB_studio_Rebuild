"""Wilson Lower Bound helper.

Pure-function module — no side effects, no logging, stdlib only.

Formula (Research §Q3):
    WLB(p̂, n) =
        [p̂ + z²/(2n)] / [1 + z²/n]
        − (z / [1 + z²/n]) × √[ p̂(1-p̂)/n + z²/(4n²) ]

Special case: accepts == 0 and total == 0 → 0.5 (neutral, "I know nothing").
This is the release-gate rule — returning 0.0 would bias every unseen clip
toward "bad" and sabotage the memory learning loop.
"""

import math


def wilson_lower_bound(accepts: int, total: int, z: float = 1.96) -> float:
    """Return the Wilson lower bound for a binary proportion.

    Args:
        accepts: Number of positive outcomes (must be >= 0 and <= total).
        total:   Total number of observations (must be >= 0).
        z:       Z-score for the desired confidence level.
                 Default 1.96 corresponds to 95 % confidence (industry standard).
                 Use 2.576 for 99 % (conservative blacklist-style gating).

    Returns:
        Wilson lower bound clamped to [0.0, 1.0].
        Returns 0.5 when total == 0 (neutral uninformed prior).

    Raises:
        ValueError: If accepts < 0, total < 0, or accepts > total.
    """
    if accepts < 0 or total < 0:
        raise ValueError(
            f"accepts and total must be non-negative, got accepts={accepts}, total={total}"
        )
    if accepts > total:
        raise ValueError(f"accepts ({accepts}) must not exceed total ({total})")

    # Release-gate rule: 0/0 → neutral 0.5 (not 0.0!)
    if total == 0:
        return 0.5

    n = total
    p_hat = accepts / n
    z2 = z * z

    centre_adjusted = p_hat + z2 / (2 * n)
    denominator = 1 + z2 / n
    spread = math.sqrt(p_hat * (1 - p_hat) / n + z2 / (4 * n * n))

    lower = (centre_adjusted - z * spread) / denominator

    # Clamp to [0.0, 1.0] to guard against floating-point drift at extremes
    return max(0.0, min(1.0, lower))


def wilson_preference_score(accepts: int, total: int, z: float = 1.96) -> float:
    """Return a neutral-centred Wilson score for candidate ranking.

    The lower confidence bound is suitable for confidence displays but not as
    a preference value beside the uninformed 0.5 fallback: Wilson(1, 1) is
    about 0.207 and would make first positive feedback a penalty.  The centre
    of the Wilson interval keeps sparse evidence shrunk towards 0.5 while
    preserving direction: accept-majority > 0.5, reject-majority < 0.5.
    """
    if accepts < 0 or total < 0:
        raise ValueError(
            f"accepts and total must be non-negative, got accepts={accepts}, total={total}"
        )
    if accepts > total:
        raise ValueError(f"accepts ({accepts}) must not exceed total ({total})")
    if total == 0:
        return 0.5

    z2 = z * z
    centre = (accepts / total + z2 / (2 * total)) / (1 + z2 / total)
    return max(0.0, min(1.0, centre))
