"""B-677: export_service._run_ffmpeg_impl braucht einen Wall-Clock-Watchdog.

Der ``timeout`` wurde nur von ``process.wait(timeout=...)`` erzwungen — das
aber erst NACH der ``for line in process.stdout``-Schleife. Haengt FFmpeg still
(stdout offen, keine Ausgabe), blockiert die Schleife in ``readline`` fuer immer
und der Timeout feuert nie. Verschaerfend laeuft der Export unter gehaltenem
``gpu_serializer`` → app-weiter NVENC-Block.

Als Stand-in fuer ein still haengendes FFmpeg dient ein Python-Prozess, der
stdout offen haelt und laenger als der Timeout nichts ausgibt.
"""

import sys
import time

import pytest

from services.export_service import _run_ffmpeg_impl


def test_silently_hanging_process_is_wall_clock_killed():
    """Ein Prozess ohne stdout-Output muss am Wall-Clock-Timeout sterben,
    nicht erst wenn er von selbst endet."""
    # Kein progress_cb / total_duration -> cmd bleibt unveraendert, stdout leer.
    hang = [sys.executable, "-c", "import time; time.sleep(12)"]

    started = time.monotonic()
    with pytest.raises(RuntimeError) as excinfo:
        _run_ffmpeg_impl(hang, timeout=1)
    elapsed = time.monotonic() - started

    assert elapsed < 6.0, (
        f"_run_ffmpeg_impl kehrte erst nach {elapsed:.1f}s zurueck — der "
        f"Wall-Clock-Watchdog greift nicht (Stand-in laeuft 12s, timeout=1s)."
    )
    assert "timeout" in str(excinfo.value).lower(), (
        f"Fehler sollte den Timeout benennen, war: {excinfo.value}"
    )


def test_fast_success_is_not_killed():
    """Ein schnell fertiger Prozess darf NICHT vom Watchdog getroffen werden."""
    ok = [sys.executable, "-c", "print('done')"]
    # timeout grosszuegig; Prozess endet in <1s mit rc=0 -> kein Raise.
    _run_ffmpeg_impl(ok, timeout=30)  # darf nicht werfen
