"""Brain V3 — WeightStore (Plan-Doc 05).

Beta-Bernoulli mit Hierarchical Backoff über 5 Levels.
Posterior-Mean = (α+1)/(α+β+2) (Laplace-Smoothing).

Lookup-Strategie: spezifischster Bucket der ≥10 Samples hat,
sonst zurück fallen auf allgemeineren Level. Wenn keiner konfident ist,
Cold-Start-Default aus services.brain.cold_start.

Single-Connection-Halter (sqlite3 ist threadlocal — diese Klasse
ist NICHT thread-safe, sondern soll von einem Worker-Thread genutzt werden).
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from services.brain.cold_start import COLD_START_DEFAULTS, BRIDGE_AXES
from services.brain.storage.sqlite_init import open_connection

logger = logging.getLogger(__name__)

MIN_CONFIDENT_SAMPLES = 10


@dataclass(frozen=True)
class AlphaBeta:
    alpha: float
    beta: float

    @property
    def n_samples(self) -> float:
        return self.alpha + self.beta

    @property
    def posterior_mean(self) -> float:
        return (self.alpha + 1.0) / (self.alpha + self.beta + 2.0)

    @property
    def variance(self) -> float:
        n = self.alpha + self.beta
        denom = (n ** 2) * (n + 1) + 1e-9
        return (self.alpha * self.beta) / denom


class WeightStore:
    """Liest + schreibt axis_weights aus weights.db."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = open_connection(self.db_path)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------
    def get_alpha_beta(self, axis: str, level: int, key: str) -> Optional[AlphaBeta]:
        row = self._get_conn().execute(
            "SELECT positive_count, negative_count FROM axis_weights "
            "WHERE axis = ? AND context_level = ? AND context_key = ?",
            (axis, level, key),
        ).fetchone()
        if row is None:
            return None
        return AlphaBeta(alpha=float(row[0]), beta=float(row[1]))

    def get_posterior_mean(
        self,
        axis: str,
        context_keys_by_level: list[str],
    ) -> float:
        """Hierarchical-Backoff-Lookup.

        Args:
            axis: Bridge-Axis-Name (siehe BRIDGE_AXES).
            context_keys_by_level: Liste mit 6 Strings (Level 0..5),
                konstruiert von services.brain.context_resolver.context_keys().

        Returns:
            Posterior-Mean des spezifischsten konfidenten Buckets,
            sonst Cold-Start-Default.
        """
        if axis not in COLD_START_DEFAULTS:
            raise ValueError(f"Unbekannte Achse: {axis!r}")
        if len(context_keys_by_level) < 1:
            return COLD_START_DEFAULTS[axis]

        # Spezifischster Level zuerst, dann zurück fallen
        for level in range(len(context_keys_by_level) - 1, -1, -1):
            key = context_keys_by_level[level]
            ab = self.get_alpha_beta(axis, level, key)
            if ab is None:
                continue
            if ab.n_samples >= MIN_CONFIDENT_SAMPLES:
                return ab.posterior_mean
        return COLD_START_DEFAULTS[axis]

    def get_variance_for_smart_sampling(
        self,
        axis: str,
        context_keys_by_level: list[str],
    ) -> float:
        """Variance des spezifischsten konfidenten Buckets — für SmartSampler.

        Bei Cold-Start (kein konfidenter Bucket) wird hohe Default-Variance
        zurückgegeben (= maximale Unsicherheit, hohe Priorität).
        """
        for level in range(len(context_keys_by_level) - 1, -1, -1):
            key = context_keys_by_level[level]
            ab = self.get_alpha_beta(axis, level, key)
            if ab is None:
                continue
            if ab.n_samples >= MIN_CONFIDENT_SAMPLES:
                return ab.variance
        # Cold-Start = α=β=0 → Variance = 0/(0*1) → handle als max
        # Bei α=β=1 (Laplace-Anker): variance = 1/(2² · 3) = 1/12 ≈ 0.083
        return 1.0 / 12.0

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
    def update(self, axis: str, level: int, key: str,
               alpha_delta: float, beta_delta: float) -> None:
        """Update einen einzelnen Bucket. Atomic via UPSERT."""
        if axis not in COLD_START_DEFAULTS:
            raise ValueError(f"Unbekannte Achse: {axis!r}")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._get_conn().execute(
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
        self._get_conn().commit()

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    def total_clicks(self) -> float:
        """Summe (positive + negative) über Level 0 = global."""
        # Level 0 hat einen einzigen Eintrag pro Achse → Summe der
        # globalen Counts ist ein Proxy für Total-Klicks.
        row = self._get_conn().execute(
            "SELECT COALESCE(SUM(positive_count + negative_count), 0) "
            "FROM axis_weights WHERE context_level = 0"
        ).fetchone()
        # Da pro Klick alle 17 Achsen × 5 Level updated werden, ist die
        # Summe im Level 0 = total_clicks * 17 * (alpha_delta+beta_delta)
        # Ein "perfect" Klick = 2.0 → 17×2.0 = 34 Inkrement total. Wir
        # geben den Roh-Wert zurück; UI kann normalisieren.
        return float(row[0]) if row else 0.0

    def top_buckets(self, n: int = 5, by: str = "positive") -> list[dict]:
        """Top-N Buckets nach positive_count (= 'positive') oder negative_count."""
        if by not in ("positive", "negative"):
            raise ValueError("by muss 'positive' oder 'negative' sein")
        order_col = "positive_count" if by == "positive" else "negative_count"
        rows = self._get_conn().execute(
            f"SELECT axis, context_level, context_key, "  # nosec B608 - interner Identifier (Tabellen-/Spaltenname aus Code-Konstante), kein User-Input; Query-Werte sind parametrisiert
            f"  positive_count, negative_count, last_updated "
            f"FROM axis_weights ORDER BY {order_col} DESC LIMIT ?",
            (n,),
        ).fetchall()
        return [
            {
                "axis": r[0], "context_level": r[1], "context_key": r[2],
                "positive_count": r[3], "negative_count": r[4],
                "last_updated": r[5],
            }
            for r in rows
        ]

    def cold_start_status(self) -> dict[str, int]:
        """Wie viele Achsen sind noch im Cold-Start (≥1 Bucket konfident)."""
        confident_axes = set()
        rows = self._get_conn().execute(
            "SELECT axis FROM axis_weights "
            "WHERE positive_count + negative_count >= ?",
            (MIN_CONFIDENT_SAMPLES,),
        ).fetchall()
        for r in rows:
            confident_axes.add(r[0])
        n_confident = len(confident_axes & set(BRIDGE_AXES))
        return {
            "total_axes": len(BRIDGE_AXES),
            "confident_axes": n_confident,
            "cold_start_axes": len(BRIDGE_AXES) - n_confident,
        }
