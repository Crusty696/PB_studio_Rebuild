from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class BudgetRule:
    """One sliding-window rule: max N hits per window_sec."""

    max_per_window: int
    window_sec: float


class VariationsBudget:
    """Parallel sliding-window counters per bucket key.

    Each bucket key (e.g. "scene_id", "style_bucket", "mood_refined", "role") has
    its own independent sliding-window counter.  A candidate cut is allowed iff
    ALL budgets for all keys present in the candidate's bucket-values are still
    under their limits.

    DJ-mix mode additionally supports segment-boundary resets (all per-segment
    budgets flushed when the track hits a structure boundary) while keeping a
    global-per-mix scene_id guard (max N uses across the entire 1-3h mix).

    Reference: Design §6.3 "Variations-Budget".
    """

    DEFAULT_BUDGETS: dict[str, BudgetRule] = {
        "scene_id": BudgetRule(max_per_window=1, window_sec=45.0),
        "style_bucket": BudgetRule(max_per_window=3, window_sec=30.0),
        "mood_refined": BudgetRule(max_per_window=4, window_sec=30.0),
        "role": BudgetRule(max_per_window=5, window_sec=30.0),
    }
    DJ_MIX_SCENE_ID_GLOBAL_MAX: int = 5  # absolute per-mix cap on single-clip reuse

    def __init__(
        self,
        budgets: Mapping[str, BudgetRule] | None = None,
        dj_mix: bool = False,
    ) -> None:
        """Args:
        budgets: dict of bucket_key → BudgetRule. Defaults to DEFAULT_BUDGETS.
        dj_mix: if True, segment_boundary() resets per-segment budgets but
                keeps the global scene_id_global counter.
        """
        self._budgets: dict[str, BudgetRule] = (
            dict(self.DEFAULT_BUDGETS) if budgets is None else dict(budgets)
        )
        self._dj_mix: bool = dj_mix

        # Per-bucket (timestamp, value) history used for sliding-window checks.
        # key → list of (ts, value) tuples
        self._history: dict[str, list[tuple[float, Any]]] = {
            key: [] for key in self._budgets
        }

        # DJ-mix global scene_id counter: value → count across entire mix.
        # Never reset by segment_boundary().
        self._scene_id_global: dict[Any, int] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def allow(self, t: float, buckets: Mapping[str, Any]) -> bool:
        """Check whether a candidate with given bucket assignments is allowed at time t.

        A candidate is allowed iff for every configured bucket_key where `buckets`
        has a value, the count within the sliding window [t - window_sec, t] is
        strictly less than max_per_window.  Bucket keys present in `buckets` but
        not in the configured rules are ignored.  Bucket keys configured but
        absent from `buckets` are skipped (cannot be evaluated).

        In DJ-mix mode, also checks the global scene_id counter
        (scene_id_global_count < DJ_MIX_SCENE_ID_GLOBAL_MAX) whenever
        `buckets` has a "scene_id" key.

        Does NOT mutate state.  Use `record()` to commit a chosen candidate.
        """
        for key, rule in self._budgets.items():
            if key not in buckets:
                continue  # key not present in candidate — skip
            value = buckets[key]
            window_start = t - rule.window_sec
            count = sum(
                1
                for ts, v in self._history.get(key, [])
                if ts >= window_start and v == value
            )
            if count >= rule.max_per_window:
                return False

        # DJ-mix global scene_id cap
        if self._dj_mix and "scene_id" in buckets:
            scene_val = buckets["scene_id"]
            global_count = self._scene_id_global.get(scene_val, 0)
            if global_count >= self.DJ_MIX_SCENE_ID_GLOBAL_MAX:
                return False

        return True

    def record(self, t: float, buckets: Mapping[str, Any]) -> None:
        """Commit a chosen candidate: append (t, value) to every configured bucket counter.

        In DJ-mix mode, also increments the global scene_id counter if a
        scene_id value is present.
        """
        for key in self._budgets:
            if key in buckets:
                self._history[key].append((t, buckets[key]))

        if self._dj_mix and "scene_id" in buckets:
            scene_val = buckets["scene_id"]
            self._scene_id_global[scene_val] = (
                self._scene_id_global.get(scene_val, 0) + 1
            )

    def segment_boundary(self, at_time: float) -> None:
        """DJ-mix only: reset per-segment sliding windows.  Keeps scene_id_global
        counter intact.  Silent no-op if dj_mix=False.

        After this call, `allow(t, ...)` for t >= at_time sees an empty
        per-segment history.
        """
        if not self._dj_mix:
            return  # silent no-op — caller may not know if this is a DJ-mix
        # Clear per-bucket histories; global counter untouched
        for key in self._history:
            self._history[key] = []
