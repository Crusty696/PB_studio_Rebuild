"""B-651: Chunked-Runner fuer tests/ui — echte Summaries trotz Native-Crash-Risiko.

Problem: Ein order-abhaengiger nativer Qt-Crash kann den Monolith-Lauf von
``pytest tests/ui`` ohne Summary toeten (Segfault, Exit ueber Pipe verschleiert).
Dieser Runner teilt tests/ui in N Subprozess-Chunks: jeder Chunk liefert eine
echte pytest-Summary, ein Crash reisst nur seinen Chunk (Rest laeuft weiter)
und wird als solcher gemeldet statt still verschluckt.

Nutzung (aus Repo-Root, direktes env-Python — kein ``conda run``, das puffert):
    python tools/run_ui_tests.py            # 4 Chunks (Default)
    python tools/run_ui_tests.py --chunks 2
    python tools/run_ui_tests.py -- -k media_grid   # Extra-Args an pytest

Exit-Code: 0 nur wenn ALLE Chunks 0 liefern.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
UI_DIR = REPO_ROOT / "tests" / "ui"
SUMMARY_RE = re.compile(r"\d+ (passed|failed|error|skipped|xfailed|deselected)")


def collect_files() -> list[Path]:
    return sorted(p for p in UI_DIR.glob("test_*.py") if p.is_file())


def chunk(files: list[Path], n: int) -> list[list[Path]]:
    n = max(1, min(n, len(files)))
    size = -(-len(files) // n)  # ceil
    return [files[i:i + size] for i in range(0, len(files), size)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chunks", type=int, default=4)
    ap.add_argument("pytest_args", nargs="*",
                    help="Extra-Argumente fuer pytest (nach '--')")
    args = ap.parse_args()

    files = collect_files()
    if not files:
        print("FEHLER: keine Testdateien in tests/ui gefunden.")
        return 2

    groups = chunk(files, args.chunks)
    print(f"tests/ui: {len(files)} Dateien in {len(groups)} Chunks "
          f"(Python: {sys.executable})")

    overall = 0
    results: list[tuple[int, int, str, float]] = []
    for i, group in enumerate(groups, 1):
        cmd = [sys.executable, "-u", "-m", "pytest", "-q",
               *args.pytest_args, *[str(p) for p in group]]
        print(f"\n=== Chunk {i}/{len(groups)}: {len(group)} Dateien ===")
        t0 = time.monotonic()
        proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True,
                              text=True, encoding="utf-8", errors="replace")
        dur = time.monotonic() - t0
        tail = (proc.stdout or "").strip().splitlines()
        summary = next((ln for ln in reversed(tail) if SUMMARY_RE.search(ln)), "")
        if proc.returncode != 0 and not summary:
            # Harter Crash ohne Summary — genau der B-651-Fall
            summary = (f"NATIVER CRASH (exit={proc.returncode}, keine "
                       f"pytest-Summary) — letzte Zeile: "
                       f"{tail[-1] if tail else '<leer>'}")
        print(f"exit={proc.returncode} ({dur:.0f}s)  {summary}")
        if proc.returncode != 0:
            overall = 1
            # Bei Fehlern die letzten Zeilen fuer Diagnose zeigen
            print("--- letzte 25 stdout-Zeilen ---")
            print("\n".join(tail[-25:]))
            if proc.stderr:
                print("--- letzte 10 stderr-Zeilen ---")
                print("\n".join(proc.stderr.strip().splitlines()[-10:]))
        results.append((i, proc.returncode, summary, dur))

    print("\n=== Gesamt ===")
    for i, rc, summary, dur in results:
        print(f"Chunk {i}: exit={rc} ({dur:.0f}s)  {summary}")
    print("ERGEBNIS:", "GRUEN" if overall == 0 else "ROT")
    return overall


if __name__ == "__main__":
    sys.exit(main())
