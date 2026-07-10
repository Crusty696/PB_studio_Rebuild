"""Workspace-Switch-Perf-Harness (Virtualisierungs-Plan M0/M4).

Misst die UI-Responsivitaet der ECHTEN App bei Workspace-Wechseln und wertet
das PB_STUDIO_FREEZE_PROBE-Profil (logs/freeze_stacks.log) aus.

Ablauf:
  1. Erwartet eine laufende PB-Studio-Instanz, gestartet mit
     PB_STUDIO_FREEZE_PROBE=1 (und optional PB_TIMELINE_PERF=1) und
     bereits geladenem Test-Projekt (z. B. test33, 1428 Cuts).
  2. Faehrt N Zyklen MATERIAL -> SCHNITT -> PROJEKT -> EXPORT per Klick.
  3. Wertet freeze_stacks.log aus: Watchdog-Dumps + Main-Thread-Hotspots.
  4. Schreibt JSON-Result nach tests/qa_artifacts/workspace_switch_perf.json.

Abnahme (Plan M4): max_watchdog_block_s <= 2.0 und alle Klicks < 2 s.

Aufruf (conda pb-studio):
  python scripts/diag/verify_workspace_switch_perf.py [--cycles 3]
"""
from __future__ import annotations

import argparse
import ctypes
import json
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FREEZE_LOG = REPO / "logs" / "freeze_stacks.log"
OUT = REPO / "tests" / "qa_artifacts" / "workspace_switch_perf.json"

NAV = {"MATERIAL": 0.371, "SCHNITT": 0.4525, "PROJEKT": 0.29, "EXPORT": 0.521}


def find_win():
    from pywinauto import Desktop
    for w in Desktop(backend="uia").windows():
        t = w.window_text()
        if "PB_studio" in t or "PB Studio" in t:
            return w
    return None


def analyze_freeze_log(offset: int) -> dict:
    if not FREEZE_LOG.exists():
        return {"watchdog_dumps": 0, "max_block_s": 0.0, "hotspots": {}}
    text = FREEZE_LOG.read_text(encoding="utf-8", errors="replace")[offset:]
    blocks = re.split(r"\n(?=Thread 0x|Current thread 0x)", text)
    hot: dict[str, int] = {}
    for b in blocks:
        if "line 2028 in main" in b or "line 2032 in <module>" in b:
            for m in re.finditer(r'File "([^"]+)", line (\d+) in (\S+)', b):
                f, ln, fn = m.groups()
                if "PB_studio_Rebuild" in f and "main.py" not in f:
                    key = f.replace("\\", "/").split("PB_studio_Rebuild/")[-1] + f":{ln} {fn}"
                    hot[key] = hot.get(key, 0) + 1
    durations = [float(m.group(1)) for m in re.finditer(r"blockiert seit (\d+(?:\.\d+)?)s", text)]
    return {
        "watchdog_dumps": len(durations),
        "max_block_s": max(durations) if durations else 0.0,
        "hotspots": dict(sorted(hot.items(), key=lambda x: -x[1])[:10]),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", type=int, default=3)
    args = ap.parse_args()

    ctypes.windll.user32.SetProcessDPIAware()
    from pywinauto import mouse

    win = find_win()
    if win is None:
        print(json.dumps({"status": "fail", "reason": "keine laufende PB-Studio-Instanz"}))
        return 1
    title = win.window_text()
    win.set_focus()
    time.sleep(1.5)
    r = win.rectangle()
    width = r.right - r.left
    nav_y = r.top + 106

    log_offset = FREEZE_LOG.stat().st_size if FREEZE_LOG.exists() else 0

    clicks = []
    for cycle in range(args.cycles):
        for name, xf in NAV.items():
            t0 = time.perf_counter()
            mouse.click(button="left", coords=(r.left + int(width * xf), nav_y))
            time.sleep(0.4)
            responsive = None
            for _ in range(90):  # bis 180s
                try:
                    w = find_win()
                    if w is not None:
                        _ = w.window_text()
                        responsive = time.perf_counter() - t0
                        break
                except Exception:
                    pass
                time.sleep(2)
            clicks.append({"cycle": cycle, "workspace": name,
                           "responsive_s": round(responsive, 2) if responsive else None})
            time.sleep(4)  # Phasen trennen

    profile = analyze_freeze_log(log_offset)
    worst_click = max((c["responsive_s"] or 999 for c in clicks), default=0)
    passed = worst_click <= 2.0 and profile["max_block_s"] <= 2.0
    result = {
        "status": "pass" if passed else "fail",
        "window_title": title,
        "cycles": args.cycles,
        "worst_click_s": worst_click,
        "clicks": clicks,
        "freeze_profile": profile,
        "acceptance": "worst_click_s <= 2.0 und max_block_s <= 2.0",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
