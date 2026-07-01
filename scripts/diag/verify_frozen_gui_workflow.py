from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FROZEN_EXE = ROOT / "dist" / "pb_studio" / "pb_studio.exe"
OUT = ROOT / "tests" / "qa_artifacts" / "frozen_gui_workflow.json"
REQUIRED_VERIFIER_MODULES = ("pygetwindow", "pywinauto", "pyautogui")


def _python_has_verifier_deps(python_exe: Path) -> bool:
    code = (
        "import importlib.util; "
        f"missing=[m for m in {REQUIRED_VERIFIER_MODULES!r} if importlib.util.find_spec(m) is None]; "
        "raise SystemExit(1 if missing else 0)"
    )
    proc = subprocess.run([str(python_exe), "-c", code], capture_output=True, text=True, check=False)
    return proc.returncode == 0


def _verifier_python() -> Path:
    candidates: list[Path] = []
    override = os.environ.get("PB_GUI_VERIFIER_PYTHON")
    if override:
        candidates.append(Path(override))
    candidates.append(Path(sys.executable))
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        candidates.append(Path(userprofile) / "miniconda3" / "envs" / "pb-studio" / "python.exe")

    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        if _python_has_verifier_deps(resolved):
            return resolved
    raise RuntimeError(
        "No Python with frozen GUI verifier dependencies found. "
        "Set PB_GUI_VERIFIER_PYTHON to a Python that can import "
        + ", ".join(REQUIRED_VERIFIER_MODULES)
        + "."
    )


def main() -> int:
    try:
        python_exe = _verifier_python()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    command = [
        str(python_exe),
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
