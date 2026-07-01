from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FROZEN_EXE = ROOT / "dist" / "pb_studio" / "pb_studio.exe"
OUT = ROOT / "tests" / "qa_artifacts" / "frozen_gui_workflow.json"


def main() -> int:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "diag" / "verify_installed_app_gui_workflow.py"),
        "--installed-exe",
        str(FROZEN_EXE),
        "--timeout",
        "120",
        "--settle-timeout",
        "45",
        "--output",
        str(OUT),
        "--artifact-label",
        "frozen_gui_workflow",
    ]
    proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False, timeout=180)
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
