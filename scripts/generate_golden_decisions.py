"""Regenerate the Golden-Run-Snapshot baseline (P14).

Runs the deterministic `build_golden_scenario()` through PacingPipeline,
serialises the rationale rows with timestamps masked (per the test contract),
and writes them to `tests/fixtures/golden_mix/expected_decisions.json`.

Usage
-----
First-ever baseline:
    python scripts/generate_golden_decisions.py --init

Intentional update (after a scoring-weights change):
    python scripts/generate_golden_decisions.py --overwrite

Dry-run (default): prints the diff summary against the current baseline and
exits non-zero if there is any drift. Does NOT touch the file.

Safety: without --overwrite or --init, the script cannot mutate the baseline.
This prevents accidental baseline drift from a stray invocation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

# Make the repo root importable even when the script is invoked from a
# different CWD (e.g. double-click on Windows, or `python scripts/...`
# from the repo root). The imports below depend on this.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.pacing.pipeline import PacingPipeline  # noqa: E402
from services.pacing.scorer import PacingScorer  # noqa: E402
from tests.fixtures.golden_mix.scenario import (  # noqa: E402
    GoldenScenario,
    build_golden_scenario,
)

# ── Public constants — the test file monkeypatches BASELINE_PATH ───────────
BASELINE_PATH: Path = (
    _REPO_ROOT / "tests" / "fixtures" / "golden_mix" / "expected_decisions.json"
)

# Float rounding for all numeric fields in the JSON snapshot.
# 6 decimals is well above numpy cosine-similarity FP noise (~1e-7) and
# below anything that could mask a real scoring regression.
FLOAT_ROUND: int = 6


# ──────────────────────────────────────────────────────────────────────────
# Snapshot building
# ──────────────────────────────────────────────────────────────────────────


def _round(v: Any) -> Any:
    """Round floats; pass other types through unchanged."""
    if isinstance(v, float):
        return round(v, FLOAT_ROUND)
    return v


def _load_weights_absolute(profile: str) -> dict[str, float]:
    """Load a weights-profile YAML via a repo-root-anchored absolute path.

    ``PacingScorer._resolve_weights`` resolves ``config/pacing_weights/<name>.yaml``
    relative to the *current working directory*, which would silently fall back
    to in-code DEFAULT_WEIGHTS whenever the script or test is invoked from any
    CWD other than the repo root. The gate's purpose is drift-detection, so we
    resolve the path explicitly here and pass the loaded mapping as ``weights=``
    to keep the baseline CWD-independent.
    """
    import yaml  # local import — only needed for baseline build

    from services.pacing.scorer import DEFAULT_WEIGHTS

    yaml_path = _REPO_ROOT / "config" / "pacing_weights" / f"{profile}.yaml"
    resolved = dict(DEFAULT_WEIGHTS)
    if yaml_path.exists():
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        for k, v in data.items():
            if k in DEFAULT_WEIGHTS:
                resolved[k] = float(v)
    return resolved


_RULES_PATH: Path = _REPO_ROOT / "config" / "pacing_rules.yaml"


def _build_pipeline(scenario: GoldenScenario) -> PacingPipeline:
    """Fresh pipeline — no DB, no DecisionRecorder, no pattern_lookup.

    We deliberately run without memory influence so the baseline is stable
    regardless of DB state; the memory term stays at its Wilson-neutral 0.5.

    Both the weights YAML (scorer) and rules YAML (pipeline) are loaded via
    repo-root-anchored absolute paths so the baseline stays identical
    regardless of the caller's CWD.
    """
    weights = _load_weights_absolute(scenario.weights_profile)
    scorer = PacingScorer(weights=weights)
    return PacingPipeline(scorer=scorer, rules_path=_RULES_PATH)


def _summarise_stage_results(stage_results: list[dict[str, Any]]) -> dict[str, int]:
    """Compress the full per-candidate stage_results into counts only.

    The full list bloats the diff and adds little signal beyond what the
    chosen-clip fields already expose. Counts still catch scoring/stage drift:
    if a new rule rejects more candidates, n_stage1_pass moves.
    """
    return {
        "n_candidates": len(stage_results),
        "n_stage1_pass": sum(1 for r in stage_results if r.get("passed_stage1")),
        "n_stage2_pass": sum(1 for r in stage_results if r.get("passed_stage2")),
        "n_soft_scored": sum(
            1 for r in stage_results if r.get("soft_score") is not None
        ),
    }


def _render_cut(
    sequence_idx: int,
    ctx: Any,
    rationale: dict[str, Any],
    chosen: Any,
) -> dict[str, Any]:
    """Render one cut's row of the golden snapshot.

    Keeps scoring-relevant outputs (chosen ids, score, contribs, stage flags).
    Strips DB ids, timestamps added by recorder, and the full stage_results list.
    """
    contribs_raw: dict[str, float] = dict(rationale.get("contribs", {}))
    contribs_rounded: dict[str, float] = {
        k: round(float(v), FLOAT_ROUND) for k, v in sorted(contribs_raw.items())
    }
    stage_results = rationale.get("stage_results", [])

    return {
        "sequence_idx": sequence_idx,
        "at_timestamp_sec": _round(ctx.at_timestamp_sec),
        "at_section_type": ctx.at_section_type,
        "at_bpm": _round(ctx.at_bpm),
        "at_genre": ctx.at_genre,
        "at_key": ctx.at_key,
        "at_mood_audio": ctx.at_mood_audio,
        "chosen_clip_id": chosen.clip_id if chosen is not None else None,
        "chosen_scene_id": chosen.scene_id if chosen is not None else None,
        "clip_role": chosen.role if chosen is not None else None,
        "clip_mood_refined": chosen.mood_refined if chosen is not None else None,
        "clip_style_bucket_id": (
            chosen.style_bucket_id if chosen is not None else None
        ),
        "chosen_score": round(float(rationale.get("chosen_score", 0.0)), FLOAT_ROUND),
        "contribs": contribs_rounded,
        "stage1_softened": bool(rationale.get("stage1_softened", False)),
        "stage2_forced": bool(rationale.get("stage2_forced", False)),
        "forced_negative": bool(rationale.get("forced_negative", False)),
        "stage_results_summary": _summarise_stage_results(stage_results),
    }


def build_snapshot(scenario: GoldenScenario | None = None) -> dict[str, Any]:
    """Run the deterministic scenario and return a JSON-serialisable snapshot.

    The snapshot has shape:
        {"cuts": [<per-cut row>, ...], "meta": {...scenario meta...}}
    """
    if scenario is None:
        scenario = build_golden_scenario()

    pipeline = _build_pipeline(scenario)
    chosen_so_far: Any = None
    rows: list[dict[str, Any]] = []
    for idx, ctx in enumerate(scenario.cuts):
        result = pipeline.select_best(
            candidates=list(scenario.candidates),
            ctx=ctx,
            predecessor=chosen_so_far,
        )
        rows.append(_render_cut(idx, ctx, result.rationale, result.chosen))
        if result.chosen is not None:
            chosen_so_far = result.chosen

    return {
        "cuts": rows,
        "meta": {
            "weights_profile": scenario.weights_profile,
            **{k: v for k, v in scenario.meta.items()},
        },
    }


def dumps_snapshot(snapshot: dict[str, Any]) -> str:
    """Deterministic JSON encoding: sorted keys, 2-space indent, trailing newline."""
    return json.dumps(snapshot, indent=2, sort_keys=True) + "\n"


# ──────────────────────────────────────────────────────────────────────────
# Diff summary (used by the script; the test has its own detailed diff)
# ──────────────────────────────────────────────────────────────────────────


def _summarise_diff(
    old: dict[str, Any],
    new: dict[str, Any],
) -> tuple[int, int, list[tuple[int, dict[str, tuple[Any, Any]]]]]:
    """Return (n_unchanged, n_drifted, list_of_drifted_details).

    drifted_details is [(sequence_idx, {field: (old_val, new_val), ...}), ...]
    """
    old_rows = {r["sequence_idx"]: r for r in old.get("cuts", [])}
    new_rows = {r["sequence_idx"]: r for r in new.get("cuts", [])}
    all_ids = sorted(set(old_rows) | set(new_rows))
    unchanged = 0
    drifted: list[tuple[int, dict[str, tuple[Any, Any]]]] = []
    for sid in all_ids:
        o = old_rows.get(sid)
        n = new_rows.get(sid)
        if o == n:
            unchanged += 1
            continue
        field_diffs: dict[str, tuple[Any, Any]] = {}
        keys = sorted(set((o or {}).keys()) | set((n or {}).keys()))
        for k in keys:
            ov = None if o is None else o.get(k)
            nv = None if n is None else n.get(k)
            if ov != nv:
                field_diffs[k] = (ov, nv)
        drifted.append((sid, field_diffs))
    return unchanged, len(drifted), drifted


def _print_diff_summary(
    old: dict[str, Any] | None,
    new: dict[str, Any],
    out: Any = sys.stdout,
) -> int:
    """Print the diff summary; return drifted count (0 means no drift)."""
    if old is None:
        print(f"[golden] No baseline yet at {BASELINE_PATH}.", file=out)
        print(f"[golden] New snapshot has {len(new.get('cuts', []))} cuts.", file=out)
        return len(new.get("cuts", []))

    unchanged, drifted_n, drifted = _summarise_diff(old, new)
    print(
        f"[golden] Unchanged: {unchanged} cuts, Drifted: {drifted_n} cuts.",
        file=out,
    )
    for sid, fields in drifted[:5]:
        print(f"  cut[{sid}]:", file=out)
        for k, (ov, nv) in fields.items():
            print(f"    {k}: {ov!r} -> {nv!r}", file=out)
    if drifted_n > 5:
        print(f"  ... and {drifted_n - 5} more drifted cuts.", file=out)
    return drifted_n


# ──────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────


def _load_existing() -> dict[str, Any] | None:
    if not BASELINE_PATH.exists():
        return None
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _write(snapshot: dict[str, Any]) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(dumps_snapshot(snapshot), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate the Golden-Run-Snapshot baseline."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the existing baseline file with the fresh snapshot.",
    )
    mode.add_argument(
        "--init",
        action="store_true",
        help="Create the baseline file if (and only if) it doesn't exist yet.",
    )
    args = parser.parse_args(argv)

    snapshot = build_snapshot()
    existing = _load_existing()

    if args.init:
        if existing is not None:
            print(
                f"[golden] --init refused: {BASELINE_PATH} already exists. "
                f"Use --overwrite to replace it.",
                file=sys.stderr,
            )
            return 2
        _write(snapshot)
        print(f"[golden] Baseline created at {BASELINE_PATH}.")
        return 0

    drifted_n = _print_diff_summary(existing, snapshot)

    if args.overwrite:
        _write(snapshot)
        print("[golden] Baseline updated.")
        return 0

    # Default dry-run mode.
    if existing is None:
        print(
            "[golden] Dry-run — no baseline exists yet. "
            "Pass --init to create it.",
            file=sys.stderr,
        )
        return 1
    if drifted_n == 0:
        print("[golden] No drift.")
        return 0
    print(
        "[golden] Dry-run — pass --overwrite to write.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
