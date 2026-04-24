"""P14 — Golden-Run-Snapshot regression gate.

Runs the deterministic `build_golden_scenario()` through PacingPipeline and
diffs the resulting per-cut rationale snapshot against a committed baseline at
`tests/fixtures/golden_mix/expected_decisions.json`.

Any change in scoring weights, stage semantics, or enrichment-side features
that feeds the scorer will move at least one contrib value by more than the
rounding floor (1e-6) and fail the test with a field-level diff. That's the
intended CI gate: you cannot silently drift the pacing logic.

Regenerating the baseline
-------------------------
Intentional changes require:

    python scripts/generate_golden_decisions.py --overwrite

The script only writes when `--overwrite` (or `--init`) is passed, so
routine runs can't accidentally clobber the baseline.
"""

from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

# `generate_golden_decisions` lives in `scripts/`; make sure it imports.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts import generate_golden_decisions  # noqa: E402
from scripts.generate_golden_decisions import (  # noqa: E402
    build_snapshot,
    dumps_snapshot,
    main as script_main,
)

# Default baseline path — the script and these tests read it from the same
# module-level constant so tests can monkeypatch it to tmp_path when needed.
BASELINE_PATH: Path = generate_golden_decisions.BASELINE_PATH


# ──────────────────────────────────────────────────────────────────────────
# Diff helper — readable per-cut field diffs
# ──────────────────────────────────────────────────────────────────────────


def _format_field_diff(
    sequence_idx: int,
    expected: dict[str, Any] | None,
    actual: dict[str, Any] | None,
) -> list[str]:
    """Return human-readable lines describing the drift on one cut row."""
    lines: list[str] = [f"--- cut[sequence_idx={sequence_idx}] ---"]
    if expected is None:
        lines.append(f"  (new cut — absent in baseline)")
        return lines
    if actual is None:
        lines.append(f"  (missing cut — present in baseline but not in fresh run)")
        return lines
    keys = sorted(set(expected.keys()) | set(actual.keys()))
    for k in keys:
        ev = expected.get(k)
        av = actual.get(k)
        if ev == av:
            continue
        lines.append(f"  {k}:")
        lines.append(f"    expected: {ev!r}")
        lines.append(f"    actual:   {av!r}")
    return lines


def _diff_report(expected: dict[str, Any], actual: dict[str, Any]) -> str:
    """Produce a multi-section diff: meta mismatch (if any) + per-cut field diffs +
    raw unified diff of the pretty-printed JSON as a last-resort fallback."""
    sections: list[str] = []

    if expected.get("meta") != actual.get("meta"):
        sections.append("--- meta ---")
        sections.append(f"  expected: {expected.get('meta')!r}")
        sections.append(f"  actual:   {actual.get('meta')!r}")

    exp_rows = {r["sequence_idx"]: r for r in expected.get("cuts", [])}
    act_rows = {r["sequence_idx"]: r for r in actual.get("cuts", [])}
    all_ids = sorted(set(exp_rows) | set(act_rows))
    drifted: list[int] = [sid for sid in all_ids if exp_rows.get(sid) != act_rows.get(sid)]
    sections.append(f"Drifted cuts: {len(drifted)} / {len(all_ids)} total")
    for sid in drifted:
        sections.extend(_format_field_diff(sid, exp_rows.get(sid), act_rows.get(sid)))

    # Unified JSON diff for context
    exp_text = dumps_snapshot(expected).splitlines(keepends=True)
    act_text = dumps_snapshot(actual).splitlines(keepends=True)
    udiff = list(
        difflib.unified_diff(
            exp_text,
            act_text,
            fromfile="expected_decisions.json",
            tofile="actual_snapshot",
            n=2,
        )
    )
    if udiff:
        sections.append("--- unified JSON diff (context n=2) ---")
        sections.append("".join(udiff))

    sections.append(
        "\nIf this change is intentional, regenerate the baseline:"
        "\n    python scripts/generate_golden_decisions.py --overwrite"
    )
    return "\n".join(sections)


# ──────────────────────────────────────────────────────────────────────────
# Core gate tests
# ──────────────────────────────────────────────────────────────────────────


def test_golden_run_snapshot_has_baseline_file() -> None:
    """Catch accidental baseline deletion before the diff test fires."""
    assert BASELINE_PATH.exists(), (
        f"Golden-Run baseline is missing at {BASELINE_PATH}. "
        f"Run: python scripts/generate_golden_decisions.py --init"
    )


def test_golden_run_snapshot_matches_baseline() -> None:
    """The pipeline output on the deterministic scenario must match the baseline.

    Any drift in scoring weights, rule matrix, stage semantics, or scorer-term
    formulas trips this — which is the point.
    """
    assert BASELINE_PATH.exists(), (
        f"Golden-Run baseline is missing at {BASELINE_PATH}. "
        f"Run: python scripts/generate_golden_decisions.py --init"
    )
    expected = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    actual = build_snapshot()

    if expected != actual:
        pytest.fail(_diff_report(expected, actual))


def test_golden_scenario_is_deterministic() -> None:
    """Two back-to-back runs in one process must yield byte-identical snapshots.

    Catches hidden randomness (e.g. an accidental `random.random()` leaking
    into a scoring helper, or dict-ordering drift on Python upgrade).
    """
    first = build_snapshot()
    second = build_snapshot()
    first_text = dumps_snapshot(first)
    second_text = dumps_snapshot(second)
    assert first_text == second_text, (
        "build_snapshot() is not deterministic across back-to-back runs.\n"
        + "".join(
            difflib.unified_diff(
                first_text.splitlines(keepends=True),
                second_text.splitlines(keepends=True),
                fromfile="first_run",
                tofile="second_run",
            )
        )
    )


def test_golden_snapshot_is_cwd_independent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Baseline must not depend on current working directory.

    PacingScorer.resolve_weights() reads config/pacing_weights/<profile>.yaml
    via a CWD-relative path; if the gate silently falls back to in-code
    DEFAULT_WEIGHTS when run from outside the repo root, the gate would
    false-positive on any run from an unusual CWD. build_snapshot() must
    load the YAML via an absolute path instead — verified here.
    """
    from_repo = build_snapshot()
    monkeypatch.chdir(tmp_path)
    from_tmp = build_snapshot()
    assert from_repo == from_tmp, (
        "Snapshot differs between CWDs — build_snapshot() has a CWD-relative "
        "dependency that would break the gate on non-repo-root invocations."
    )


# ──────────────────────────────────────────────────────────────────────────
# Script tests — ensure the regeneration helper is safe and functional
# ──────────────────────────────────────────────────────────────────────────


def test_script_init_writes_file_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--init creates the baseline from scratch when the file is absent."""
    fake_path = tmp_path / "expected_decisions.json"
    monkeypatch.setattr(generate_golden_decisions, "BASELINE_PATH", fake_path)
    assert not fake_path.exists()

    rc = script_main(["--init"])
    assert rc == 0, "--init should succeed when baseline is missing"
    assert fake_path.exists(), "--init should have written the baseline file"

    # Sanity: the file parses as JSON with the expected top-level keys.
    data = json.loads(fake_path.read_text(encoding="utf-8"))
    assert "cuts" in data
    assert "meta" in data
    assert len(data["cuts"]) > 0


def test_script_init_refuses_when_file_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--init must refuse if the baseline already exists (prevents accidental reset)."""
    fake_path = tmp_path / "expected_decisions.json"
    fake_path.write_text('{"existing": true}\n', encoding="utf-8")
    monkeypatch.setattr(generate_golden_decisions, "BASELINE_PATH", fake_path)

    rc = script_main(["--init"])
    assert rc != 0, "--init should fail when baseline exists"
    # Original content untouched
    assert fake_path.read_text(encoding="utf-8") == '{"existing": true}\n'


def test_script_dry_run_exits_nonzero_on_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dry-run with a stale baseline must report drift and exit non-zero without writing."""
    fake_path = tmp_path / "expected_decisions.json"
    stale = {"cuts": [{"sequence_idx": 0, "stale": True}], "meta": {"stale": True}}
    fake_path.write_text(json.dumps(stale) + "\n", encoding="utf-8")
    monkeypatch.setattr(generate_golden_decisions, "BASELINE_PATH", fake_path)

    rc = script_main([])
    assert rc != 0, "dry-run should exit non-zero when drift is detected"

    # File unchanged — dry-run must never write.
    data = json.loads(fake_path.read_text(encoding="utf-8"))
    assert data == stale, "dry-run mutated the baseline (it must not)"


def test_script_dry_run_zero_on_no_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the baseline matches the fresh snapshot, dry-run exits 0."""
    fake_path = tmp_path / "expected_decisions.json"
    fresh = build_snapshot()
    fake_path.write_text(dumps_snapshot(fresh), encoding="utf-8")
    monkeypatch.setattr(generate_golden_decisions, "BASELINE_PATH", fake_path)

    rc = script_main([])
    assert rc == 0, "dry-run should exit 0 when snapshots match"


def test_script_overwrite_updates_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--overwrite replaces a stale baseline with the fresh snapshot."""
    fake_path = tmp_path / "expected_decisions.json"
    fake_path.write_text('{"cuts":[],"meta":{"stale":true}}\n', encoding="utf-8")
    monkeypatch.setattr(generate_golden_decisions, "BASELINE_PATH", fake_path)

    rc = script_main(["--overwrite"])
    assert rc == 0, "--overwrite should succeed"

    after = json.loads(fake_path.read_text(encoding="utf-8"))
    fresh = build_snapshot()
    assert after == fresh, "baseline after --overwrite must equal the fresh snapshot"


def test_script_creates_parent_dir_when_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--init must create the parent directory if it doesn't exist."""
    fake_path = tmp_path / "nested" / "never" / "created" / "expected_decisions.json"
    monkeypatch.setattr(generate_golden_decisions, "BASELINE_PATH", fake_path)

    rc = script_main(["--init"])
    assert rc == 0
    assert fake_path.exists()
