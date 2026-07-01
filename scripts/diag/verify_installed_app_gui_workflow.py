from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "tests" / "qa_artifacts"
OUT = ARTIFACT_DIR / "installed_app_gui_workflow.json"
DEFAULT_INSTALLED_EXE = Path(r"C:\Program Files\PB Studio\pb_studio.exe")
PROOF_PATH = ROOT / "docs" / "superpowers" / "synthesis" / "installed-app-gui-live-proof-2026-07-01.md"


def _write_json(payload: dict[str, object]) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _running(pid: int) -> bool:
    if sys.platform == "win32":
        proc = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
            capture_output=True,
            text=True,
            check=False,
        )
        return str(pid) in (proc.stdout or "")
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _wait_for_window(title_fragment: str, timeout_s: float) -> dict[str, object] | None:
    import pygetwindow as gw

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for window in gw.getAllWindows():
            title = window.title or ""
            if title_fragment not in title:
                continue
            if window.width < 400 or window.height < 300:
                continue
            if window.left < -10000 or window.top < -10000:
                continue
            try:
                if window.isMinimized:
                    window.restore()
                window.activate()
            except Exception:
                pass
            return {
                "title": title,
                "left": window.left,
                "top": window.top,
                "width": window.width,
                "height": window.height,
            }
        time.sleep(0.5)
    return None


def _screenshot(label: str, window: dict[str, object]) -> str:
    import pyautogui

    path = ARTIFACT_DIR / f"{label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    image = pyautogui.screenshot()
    left = max(0, int(window["left"]))
    top = max(0, int(window["top"]))
    right = left + int(window["width"])
    bottom = top + int(window["height"])
    image.crop((left, top, right, bottom)).save(path)
    return str(path)


def _uia_labels(title_fragment: str) -> list[str]:
    import pygetwindow as gw
    from pywinauto import Application

    target = None
    for window in gw.getAllWindows():
        if title_fragment in (window.title or "") and window.width >= 400 and window.height >= 300:
            target = window
            break
    if target is None:
        return []
    app = Application(backend="uia").connect(handle=target._hWnd, timeout=10)
    top = app.window(handle=target._hWnd)
    labels: list[str] = []
    for element in top.descendants():
        try:
            text = (element.window_text() or "").strip()
        except Exception:
            continue
        if text:
            labels.append(text)
        if len(labels) >= 250:
            break
    return labels


def _close_process(proc: subprocess.Popen[object], pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid)], capture_output=True, check=False)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if not _running(pid):
                return
            time.sleep(0.5)
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, check=False)
        return
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()


def _write_proof(result: dict[str, object], screenshot_path: str) -> None:
    text = f"""---
release_gate_proof: true
proof_type: installed-app-gui
status: pass
evidence_level: live
---

# Installed-App GUI Live Proof 2026-07-01

## Scope

This proof was generated only after launching the installed PB Studio EXE and
observing the real GUI window.

## Evidence

- Installed EXE: `{result["installed_exe"]}`
- PID: `{result["pid"]}`
- Window title: `{result["window_title"]}`
- Screenshot: `{screenshot_path}`
- Required labels observed: `{", ".join(result["required_labels_observed"])}`.

## Limit

This proof only covers installed-app GUI launch/navigation shell readiness. It
does not prove code signing, clean-VM installation, or the DG-001 H1 user
decision.
"""
    PROOF_PATH.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--installed-exe", default=os.environ.get("PB_INSTALLED_EXE", str(DEFAULT_INSTALLED_EXE)))
    parser.add_argument("--window-title", default="PB_studio")
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--write-proof", action="store_true")
    args = parser.parse_args()

    installed_exe = Path(args.installed_exe)
    if not installed_exe.is_file():
        result = {
            "status": "blocked",
            "installed_app_gui_workflow_passed": False,
            "installed_exe": str(installed_exe),
            "blockers": ["installed-exe-missing"],
            "proof_written": False,
            "note": "No installed-app GUI proof can be created without the installed EXE.",
        }
        _write_json(result)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2

    env = os.environ.copy()
    env["PB_CLICK_LOG"] = "1"
    proc = subprocess.Popen([str(installed_exe)], cwd=str(installed_exe.parent), env=env)
    screenshot_path = ""
    try:
        window = _wait_for_window(args.window_title, args.timeout)
        labels = _uia_labels(args.window_title) if window else []
        required = [
            "Projekt Workflow",
            "Material und Analyse Workflow",
            "Schnitt Workflow",
            "Export Workflow",
        ]
        observed = [label for label in required if any(label in seen for seen in labels)]
        time.sleep(5)
        alive = _running(proc.pid)
        if window:
            screenshot_path = _screenshot("installed_app_gui_workflow", window)
        passed = bool(window and alive and len(observed) == len(required))
        result = {
            "status": "pass" if passed else "fail",
            "installed_app_gui_workflow_passed": passed,
            "installed_exe": str(installed_exe),
            "pid": proc.pid,
            "process_alive_after_5s": alive,
            "window_title": window["title"] if window else None,
            "window": window,
            "required_labels_observed": observed,
            "required_labels_missing": [label for label in required if label not in observed],
            "screenshot": screenshot_path,
            "proof_written": False,
            "proof_path": str(PROOF_PATH),
        }
        if passed and args.write_proof:
            _write_proof(result, screenshot_path)
            result["proof_written"] = True
        _write_json(result)
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0 if passed else 1
    finally:
        _close_process(proc, proc.pid)


if __name__ == "__main__":
    raise SystemExit(main())
