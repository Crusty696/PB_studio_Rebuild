"""Re-generate the bridge-mapping snapshot baseline.

Usage:
    python scripts/generate_pacing_baseline.py --overwrite

Schreibt nach `tests/integration/baselines/pacing_bridge_snapshot.json`.
Ohne `--overwrite` wird ein bestehender Baseline NICHT ersetzt.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Reuse the test fixture builder so baseline & snapshot stay aligned
from tests.integration.test_pacing_bridge_snapshot import (
    BASELINE_PATH,
    _build_fixture_outputs,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--overwrite", action="store_true",
                        help="Überschreibt eine vorhandene Baseline.")
    args = parser.parse_args()

    if BASELINE_PATH.exists() and not args.overwrite:
        print(f"Baseline existiert bereits: {BASELINE_PATH}")
        print("Mit --overwrite ersetzen.")
        sys.exit(1)

    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = _build_fixture_outputs()
    BASELINE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Baseline geschrieben: {BASELINE_PATH}")


if __name__ == "__main__":
    main()
