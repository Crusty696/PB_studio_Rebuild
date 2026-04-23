from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Sequence

import numpy as np
import yaml

from services.pacing.scorer import (
    AudioContext,
    ClipFeatures,
    PacingScorer,
)
from services.pacing.variations_budget import BudgetRule, VariationsBudget

if TYPE_CHECKING:
    from services.pacing.decision_recorder import DecisionRecorder


@dataclass
class StageResult:
    """Per-candidate stage-by-stage trace for an auditable rationale."""

    clip_id: int
    passed_stage1: bool
    passed_stage2: bool
    collision_similarity: float | None  # set by Stage 3 (None if no predecessor)
    soft_score: float | None  # set by Stage 4 only for surviving candidates
    contribs: dict[str, float] = field(default_factory=dict)
    rejected_reason: str | None = (
        None  # "role_mismatch" | "key_mood_gate" | "budget_full" | None
    )
    budget_keys_failed: list[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    """Final output of one select_best() call.

    Either (chosen, rationale) with chosen non-None, or a fallback case
    with chosen=None + rationale detailing why nothing was pickable —
    this should be RARE; the pipeline is designed to always produce a
    cut via stage-1 softening and forced top-K.
    """

    chosen: ClipFeatures | None
    rationale: dict[
        str, Any
    ]  # json-serializable; persisted into mem_decision.agent_rationale


class PacingPipeline:
    """4-stage candidate selection for the pacing agent.

    Stage 1 — Hard Rules (Section × Role matrix)
        Reject candidates whose role is not allowed for the current
        section_type. If 0 candidates survive and `stage1_fallback=="soften"`,
        widen the role set and retry. If still 0, return PipelineResult(None, ...).

    Stage 2 — Variations Budget (parallel sliding-window counters)
        Reject candidates whose selection would exceed any per-bucket budget.
        If 0 candidates survive, loosen by allowing the clip with LOWEST
        per-bucket excess, flagged as "forced=true".

    Stage 3 — Collision Check (per Design §6.4 — PENALTY, not hard-reject)
        For every surviving candidate, compute cosine similarity to the
        predecessor clip's embedding. If < `collision_min_similarity`
        (default 0.55), the clip proceeds but with a collision flag that
        the scorer's `w_collision` term penalizes. Hard-reject path only
        activates when the profile has `collision_strict=true` (default off).

    Stage 4 — Soft Scoring (all 13 weighted terms)
        Call PacingScorer on every surviving candidate. Sort by total,
        pick the top one. If all totals are negative, still pick the top
        one (least-bad), with `forced=true` in the rationale.

    The result's rationale dict is the payload written into mem_decision.agent_rationale.
    """

    def __init__(
        self,
        scorer: PacingScorer | None = None,
        rules_path: str | Path = "config/pacing_rules.yaml",
        budgets: Mapping[str, BudgetRule] | None = None,
        dj_mix: bool = False,
        collision_min_similarity: float = 0.55,
        collision_strict: bool = False,
        decision_recorder: "DecisionRecorder | None" = None,
        run_id: int | None = None,
    ) -> None:
        self._scorer = scorer or PacingScorer(weights_profile="default")
        self._rules = self._load_rules(rules_path)
        self._budget = VariationsBudget(budgets=budgets, dj_mix=dj_mix)
        self._collision_min_similarity = collision_min_similarity
        self._collision_strict = collision_strict
        self._recorder: "DecisionRecorder | None" = decision_recorder
        self._run_id: int | None = run_id
        self._sequence_idx: int = 0

    def reset_sequence(self, run_id: int | None = None) -> None:
        """Reset the internal sequence counter. Call between runs when reusing a pipeline."""
        self._sequence_idx = 0
        if run_id is not None:
            self._run_id = run_id

    @staticmethod
    def _load_rules(path: str | Path) -> dict[str, Any]:
        """Load section_role_matrix + key_mood_gate + stage1_fallback from YAML.
        Falls back to in-code defaults if file missing (tests that don't care about
        rules can instantiate without touching disk)."""
        rules_path = Path(path)
        if not rules_path.exists():
            return {
                "section_role_matrix": {},
                "key_mood_gate": {"enabled": False, "forbidden_moods": []},
                "stage1_fallback": "soften",
            }
        try:
            data: dict[str, Any] = (
                yaml.safe_load(rules_path.read_text(encoding="utf-8")) or {}
            )
            return data
        except (yaml.YAMLError, OSError):
            return {
                "section_role_matrix": {},
                "key_mood_gate": {"enabled": False, "forbidden_moods": []},
                "stage1_fallback": "soften",
            }

    def select_best(
        self,
        candidates: Sequence[ClipFeatures],
        ctx: AudioContext,
        predecessor: ClipFeatures | None = None,
        recent_clip_ids: Sequence[int] | None = None,
    ) -> PipelineResult:
        """Run all 4 stages and return (chosen, rationale)."""
        if not candidates:
            return PipelineResult(
                chosen=None,
                rationale={
                    "error": "no_candidates",
                    "stage_results": [],
                },
            )

        # === Stage 1 — Hard Rules (Section × Role) ===
        stage_results: list[StageResult] = [
            StageResult(
                clip_id=c.clip_id,
                passed_stage1=self._stage1_accepts(c, ctx),
                passed_stage2=False,
                collision_similarity=None,
                soft_score=None,
            )
            for c in candidates
        ]
        stage1_survivors = [
            c for c, r in zip(candidates, stage_results) if r.passed_stage1
        ]
        stage1_softened = False
        if not stage1_survivors:
            if self._rules.get("stage1_fallback", "soften") == "soften":
                # Widen: accept filler/unknown roles too
                for c, r in zip(candidates, stage_results):
                    if c.role in {"filler", "unknown"}:
                        r.passed_stage1 = True
                        r.rejected_reason = None
                stage1_survivors = [
                    c for c, r in zip(candidates, stage_results) if r.passed_stage1
                ]
                stage1_softened = True
            if not stage1_survivors:
                return PipelineResult(
                    chosen=None,
                    rationale={
                        "error": "stage1_no_candidates",
                        "softened": stage1_softened,
                        "stage_results": [vars(r) for r in stage_results],
                    },
                )

        # === Stage 2 — Variations Budget ===
        # Evaluate each survivor against the budget (non-mutating)
        for c, r in zip(candidates, stage_results):
            if not r.passed_stage1:
                continue
            buckets = self._candidate_buckets(c)
            allowed = self._budget.allow(ctx.at_timestamp_sec, buckets)
            r.passed_stage2 = allowed
            if not allowed:
                r.rejected_reason = "budget_full"
                r.budget_keys_failed = self._which_budgets_failed(
                    c, ctx.at_timestamp_sec
                )

        stage2_survivors = [
            c for c, r in zip(candidates, stage_results) if r.passed_stage2
        ]
        stage2_forced = False
        if not stage2_survivors:
            # Forced fallback: accept all stage1_survivors (budget overridden)
            for c, r in zip(candidates, stage_results):
                if r.passed_stage1:
                    r.passed_stage2 = True
                    r.rejected_reason = None
            stage2_survivors = stage1_survivors
            stage2_forced = True

        # === Stage 3 — Collision Check (penalty; hard-reject only if strict) ===
        for c, r in zip(candidates, stage_results):
            if not r.passed_stage2:
                continue
            if (
                predecessor is None
                or predecessor.embedding is None
                or c.embedding is None
            ):
                r.collision_similarity = None  # can't compute; not a collision
                continue
            a = predecessor.embedding
            b = c.embedding
            na = float(np.linalg.norm(a))
            nb = float(np.linalg.norm(b))
            if na < 1e-9 or nb < 1e-9:
                r.collision_similarity = None
                continue
            sim = float(np.dot(a, b) / (na * nb))
            r.collision_similarity = sim
            # Hard-reject path: only if collision_strict
            if self._collision_strict and sim < self._collision_min_similarity:
                r.passed_stage2 = False  # repurpose: stage2 flag also gates stage4
                r.rejected_reason = "collision_strict"

        stage3_survivors = [
            c for c, r in zip(candidates, stage_results) if r.passed_stage2
        ]
        if not stage3_survivors:
            # Collision-strict killed everyone: drop the strict filter for this cut
            # (classic Rule: never empty-cut).
            for c, r in zip(candidates, stage_results):
                if r.rejected_reason == "collision_strict":
                    r.passed_stage2 = True
                    r.rejected_reason = None
            stage3_survivors = [
                c for c, r in zip(candidates, stage_results) if r.passed_stage2
            ]

        # === Stage 4 — Soft Scoring ===
        scored: list[tuple[ClipFeatures, float, dict[str, float]]] = []
        for c, r in zip(candidates, stage_results):
            if not r.passed_stage2:
                continue
            total, contribs = self._scorer.score(
                c, ctx, predecessor=predecessor, recent_clip_ids=recent_clip_ids
            )
            r.soft_score = total
            r.contribs = dict(contribs)
            scored.append((c, total, contribs))

        if not scored:
            return PipelineResult(
                chosen=None,
                rationale={
                    "error": "stage4_no_candidates",
                    "stage_results": [vars(r) for r in stage_results],
                },
            )

        scored.sort(key=lambda t: t[1], reverse=True)
        best_clip, best_score, best_contribs = scored[0]
        forced_negative = best_score < 0.0

        # Commit the chosen candidate to the budget (mutate state)
        self._budget.record(ctx.at_timestamp_sec, self._candidate_buckets(best_clip))

        rationale: dict[str, Any] = {
            "chosen_clip_id": best_clip.clip_id,
            "chosen_scene_id": best_clip.scene_id,
            "chosen_score": best_score,
            "contribs": best_contribs,
            "stage1_softened": stage1_softened,
            "stage2_forced": stage2_forced,
            "forced_negative": forced_negative,
            "stage_results": [vars(r) for r in stage_results],
            "at_section_type": ctx.at_section_type,
        }

        # === DecisionRecorder integration (Bug F fix) ===
        # The recorder MUST be called here — not in a wrapper, not optionally in the
        # caller — so that every select_best() call that produces a chosen clip lands
        # a row in mem_decision.  If no recorder is injected (e.g. in tests that
        # don't care about persistence), the guard makes this a no-op.
        if (
            self._recorder is not None
            and self._run_id is not None
            and best_clip is not None
        ):
            decision_id = self._recorder.record(
                run_id=self._run_id,
                sequence_idx=self._sequence_idx,
                ctx=ctx,
                chosen=best_clip,
                rationale=rationale,
                agent_score=best_score,
            )
            rationale["persisted_decision_id"] = decision_id
            self._sequence_idx += 1

        return PipelineResult(chosen=best_clip, rationale=rationale)

    # ── Helpers ────────────────────────────────────────────────────────────

    def _stage1_accepts(self, c: ClipFeatures, ctx: AudioContext) -> bool:
        """True iff c's role is allowed for ctx.section_type per the matrix.
        Also applies the optional key_mood_gate when enabled and tension > threshold."""
        section = (ctx.at_section_type or "").lower()
        matrix: dict[str, list[str]] = self._rules.get("section_role_matrix", {}) or {}
        allowed: list[str] = matrix.get(section, []) or []
        if section and allowed and c.role not in allowed:
            return False

        # key_mood_gate (optional, default disabled)
        gate: dict[str, Any] = self._rules.get("key_mood_gate", {}) or {}
        if gate.get("enabled") and ctx.at_harmonic_tension is not None:
            # Simple tension > 0.7 check (matches spec example)
            if ctx.at_harmonic_tension > 0.7:
                forbidden = set(gate.get("forbidden_moods", []) or [])
                if c.mood_refined in forbidden:
                    return False
        return True

    def _candidate_buckets(self, c: ClipFeatures) -> dict[str, Any]:
        """Map a ClipFeatures to the bucket keys VariationsBudget expects."""
        return {
            "scene_id": c.scene_id,
            "style_bucket": c.style_bucket_id,
            "mood_refined": c.mood_refined,
            "role": c.role,
        }

    def _which_budgets_failed(self, c: ClipFeatures, t: float) -> list[str]:
        """Introspect: for each configured bucket key, check if adding c would exceed.

        NOTE: VariationsBudget stores history in `_history` (not `_histories`).
        This is a read-only diagnostic — never mutates budget state.
        """
        failed: list[str] = []
        for key, rule in self._budget._budgets.items():
            history = self._budget._history.get(key, [])
            value = self._candidate_buckets(c).get(key)
            if value is None:
                continue
            window_start = t - rule.window_sec
            in_window = [
                (ts, val) for ts, val in history if ts >= window_start and val == value
            ]
            if len(in_window) >= rule.max_per_window:
                failed.append(key)
        return failed
