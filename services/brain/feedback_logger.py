"""Brain V3 — FeedbackLogger (Plan-Doc 05).

Atomic-Update aller 6 Backoff-Levels (0..5) × 17 Achsen = 102 Buckets pro Klick,
in EINER Transaktion via UPSERT.

Roh-Klick-Log in feedback_events (state.db) ist Phase-4-Zuständigkeit
und nicht hier.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal

from services.brain.cold_start import BRIDGE_AXES
from services.brain.weight_store import WeightStore

logger = logging.getLogger(__name__)

Rating = Literal["perfect", "fits", "not_quite", "no_match"]

# Plan-Doc 05 Tabelle
RATING_MAP: dict[str, tuple[float, float]] = {
    "perfect":   (2.0, 0.0),
    "fits":      (1.0, 0.0),
    "not_quite": (0.0, 1.0),
    "no_match":  (0.0, 2.0),
}


class FeedbackLogger:
    """Atomic-Update auf weights.db pro Klick."""

    def __init__(self, weights: WeightStore):
        self.weights = weights

    def log_feedback(
        self,
        rating: str,
        context_keys_by_level: list[str],
    ) -> dict:
        """Atomarer Update aller 102 Buckets in einer Transaktion.

        Args:
            rating: 'perfect' | 'fits' | 'not_quite' | 'no_match'
            context_keys_by_level: Liste mit 6 Strings (Level 0..5),
                                   konstruiert via context_resolver.context_keys()

        Returns:
            Diagnostik-Dict mit alpha_delta, beta_delta, n_buckets_updated.

        Raises:
            ValueError bei unbekanntem Rating.
        """
        if rating not in RATING_MAP:
            raise ValueError(f"Unbekanntes Rating: {rating!r}. Verfügbar: {list(RATING_MAP)}")
        if len(context_keys_by_level) != 6:
            raise ValueError(
                f"context_keys_by_level muss 6 Einträge haben (Level 0..5), "
                f"hatte {len(context_keys_by_level)}"
            )

        alpha_delta, beta_delta = RATING_MAP[rating]
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conn = self.weights._get_conn()

        # WICHTIG: BEGIN…COMMIT macht ALLE Updates atomar
        try:
            conn.execute("BEGIN")
            for axis in BRIDGE_AXES:
                for level, key in enumerate(context_keys_by_level):
                    conn.execute(
                        """
                        INSERT INTO axis_weights
                            (axis, context_level, context_key,
                             positive_count, negative_count, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(axis, context_level, context_key) DO UPDATE SET
                            positive_count = positive_count + ?,
                            negative_count = negative_count + ?,
                            last_updated   = excluded.last_updated
                        """,
                        (axis, level, key, alpha_delta, beta_delta, now,
                         alpha_delta, beta_delta),
                    )
            conn.commit()
        except Exception:
            conn.execute("ROLLBACK")
            raise

        n_updated = len(BRIDGE_AXES) * len(context_keys_by_level)
        logger.info("FeedbackLogger.log_feedback rating=%s α=+%.1f β=+%.1f → %d buckets",
                    rating, alpha_delta, beta_delta, n_updated)
        return {
            "rating": rating,
            "alpha_delta": alpha_delta,
            "beta_delta": beta_delta,
            "n_buckets_updated": n_updated,
        }
