"""B-706/F5: ffmpeg_runner — stdout gehoert exklusiv dem Progress-Reader.

Vorher las ``communicate()`` stdout PARALLEL zum ``_progress_reader``-Thread ->
die beiden teilten sich die Progress-Zeilen (ruckelnder LUFS-Balken). Jetzt wird
stderr in einem eigenen Thread gedraint und nur auf den Prozess gewartet; stdout
liest ausschliesslich der Progress-Reader.

F5 ist ein Race ohne Korrektheitsfehler — ein deterministisches RED laesst sich
nicht stabil reproduzieren. Dieser Test ist ein Verhaltens-Guard fuer die
Fix-Implementierung: alle Progress-Zeilen kommen an, stderr wird VOLLSTAENDIG
eingefangen, und der Lauf blockiert nicht (kein Pipe-Deadlock).
"""
from __future__ import annotations

import sys

from services.export import ffmpeg_runner


def test_b706_f5_progress_complete_and_stderr_fully_captured():
    # Fake-"ffmpeg": 5 Progress-Zeilen auf stdout, 5 Diagnose-Zeilen auf stderr.
    script = (
        "import sys\n"
        "for i in range(1, 6):\n"
        "    sys.stdout.write('out_time_ms=%d\\n' % (i * 1000000))\n"
        "    sys.stdout.flush()\n"
        "    sys.stderr.write('frame=%d stderr-line\\n' % i)\n"
        "    sys.stderr.flush()\n"
    )
    cmd = [sys.executable, "-c", script]

    seen: list[int] = []

    def cb(pct, msg):
        seen.append(pct)

    result = ffmpeg_runner._run_subprocess_cancellable(
        cmd, timeout=30, progress_cb=cb, total_duration=5.0,
    )

    assert result.returncode == 0
    # stderr vollstaendig eingefangen (kein Verlust durch Doppel-Read).
    assert result.stderr.count("stderr-line") == 5
    # Reader besitzt stdout exklusiv -> jede der 5 Progress-Zeilen loest cb aus.
    assert len(seen) == 5
    # out_time_ms=5s / total 5s -> 100%, auf 99 gedeckelt.
    assert max(seen) <= 99


def test_b706_f5_large_stderr_no_deadlock():
    """Viel stderr (> 64KB Pipe-Buffer) darf nicht deadlocken — stderr wird
    nebenlaeufig gedraint."""
    script = (
        "import sys\n"
        "for i in range(1, 4):\n"
        "    sys.stdout.write('out_time_ms=%d\\n' % (i * 1000000))\n"
        "    sys.stdout.flush()\n"
        "for _ in range(5000):\n"
        "    sys.stderr.write('x' * 100 + '\\n')\n"
    )
    cmd = [sys.executable, "-c", script]
    result = ffmpeg_runner._run_subprocess_cancellable(
        cmd, timeout=30, progress_cb=lambda p, m: None, total_duration=3.0,
    )
    assert result.returncode == 0
    assert len(result.stderr) > 64 * 1024, "grosses stderr muss vollstaendig gelesen werden"
