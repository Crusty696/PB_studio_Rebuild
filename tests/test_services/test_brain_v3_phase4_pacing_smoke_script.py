from __future__ import annotations

import json
import os
import subprocess
import sys


def test_phase4_pacing_smoke_reports_compare_and_timings() -> None:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"

    proc = subprocess.run(
        [sys.executable, "scripts/spike_brain_v3_pacing_smoke.py"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(proc.stdout)

    assert data["checks"]["pacing_compare_ran"] is True
    assert data["checks"]["pacing_overhead_under_800ms"] is True
    assert data["checks"]["learning_session_under_2s"] is True
    assert data["pacing_compare"]["baseline"]["chosen_clip_id"] is not None
    assert data["pacing_compare"]["brain_v3"]["chosen_clip_id"] is not None
    assert data["pacing_compare"]["brain_v3"]["used_brain_v3"] is True
    assert data["timings_ms"]["pacing_overhead"] < 800.0
    assert data["timings_ms"]["learning_session"] < 2000.0
    assert data["learning_session"]["requested_n"] == 15
