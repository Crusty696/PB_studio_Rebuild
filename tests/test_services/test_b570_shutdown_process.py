"""B-570: real Qt child process must exit with cancelled live QThread."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def test_cancelled_live_qthread_does_not_keep_app_process_alive():
    repo_root = Path(__file__).resolve().parents[2]
    child = repo_root / "tests" / "repro" / "b570_shutdown_child.py"
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"

    try:
        result = subprocess.run(
            [sys.executable, str(child)],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            # B-592: Das Budget lag bei 45 s, aber allein `import main` braucht
            # auf diesem Rechner rund 34 s (gemessen 2026-08-11: torch 4.8 s,
            # ui 2.7 s, der Rest im main-Modulkoerper). Der Kindprozess
            # importiert main, fuehrt danach das eigentliche Szenario aus und
            # faehrt herunter — das passte nicht mehr zuverlaessig hinein.
            # Deshalb war der Test seriell knapp gruen und im parallelen Lauf
            # rot, was jahrelang als "Test-Pollution" gedeutet wurde.
            #
            # Widerlegt: der dGPU-Wake-Check in main.py ist NICHT die Ursache.
            # Messung mit und ohne uebersprungenen Check: 34.4 s gegen 35.1 s.
            # Er kostet nichts, solange die GPU wach ist.
            #
            # Das Budget deckt jetzt den gemessenen Import plus Reserve. Die
            # lange Importzeit selbst bleibt ein eigenes Thema — sie ist auch
            # die Startzeit der App und gehoert dort behandelt, nicht hier
            # wegoptimiert.
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output = f"{exc.stdout or ''}\n{exc.stderr or ''}"
        raise AssertionError(f"B-570 child timeout:\n{output}") from exc

    output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode == 0, output
    assert (
        "B570_CHILD_EXIT_OK" in output
        or "B570_CHILD_WAITING_HARD_EXIT" in output
    ), output
    assert "B570_CHILD_HARD_EXIT_MISSING" not in output
