"""B-467: Export-Progress-Parser darf ``out_time_ms=N/A`` nicht als Fehler werten.

FFmpeg schreibt im ersten ``-progress pipe:1``-Frame oft ``out_time_ms=N/A``
(noch kein Output). Frueher lief das in ``int("N/A")`` -> ValueError -> WARNING.
Der Export selbst war nie betroffen (Exception wurde gefangen), aber das Log
bekam eine irrefuehrende Warnung. Nach dem Fix wird ``N/A`` still uebersprungen,
gueltige Frames erzeugen weiter Progress-Updates.
"""

from __future__ import annotations

import logging

from unittest.mock import patch

import services.export_service as export_service


class _FakePopen:
    """Minimaler Popen-Ersatz: liefert vordefinierte stdout-Zeilen."""

    def __init__(self, stdout_lines):
        self.stdout = iter(stdout_lines)
        self.stderr = iter([])
        self.returncode = 0

    def poll(self):
        return 0  # bereits beendet -> kein kill() im finally

    def wait(self, timeout=None):
        return 0

    def terminate(self):
        pass

    def kill(self):
        pass


def _run_with_lines(lines):
    progress_calls: list[tuple[int, str]] = []

    def progress_cb(pct, msg):
        progress_calls.append((pct, msg))

    fake = _FakePopen(lines)
    with patch.object(export_service.subprocess, "Popen", return_value=fake):
        export_service._run_ffmpeg_impl(
            ["ffmpeg", "-y", "out.mp4"],
            timeout=5,
            progress_cb=progress_cb,
            total_duration=10.0,
        )
    return progress_calls


def test_b467_out_time_ms_na_does_not_warn(caplog):
    """``out_time_ms=N/A`` -> keine WARNING, gueltiger Frame -> Progress-Update."""
    lines = [
        "out_time_ms=N/A\n",
        "out_time_ms=5000000\n",  # 5.0s von 10s -> 50%
        "progress=continue\n",
    ]
    with caplog.at_level(logging.WARNING, logger="services.export_service"):
        progress_calls = _run_with_lines(lines)

    warnings = [
        r.getMessage() for r in caplog.records
        if "out_time_ms progress" in r.getMessage()
    ]
    assert warnings == [], f"B-467: N/A loggte eine WARNING: {warnings}"
    assert progress_calls == [(50, "Rendering 50%...")], (
        f"B-467: gueltiger Frame erzeugte kein/falsches Progress-Update: {progress_calls}"
    )


def test_b467_out_time_na_does_not_warn(caplog):
    """Gleiche N/A-Behandlung fuer den ``out_time=``-Branch."""
    lines = [
        "out_time=N/A\n",
        "out_time=00:00:05.00\n",  # 5.0s von 10s -> 50%
    ]
    with caplog.at_level(logging.WARNING, logger="services.export_service"):
        progress_calls = _run_with_lines(lines)

    warnings = [
        r.getMessage() for r in caplog.records
        if "out_time progress" in r.getMessage()
    ]
    assert warnings == [], f"B-467: out_time=N/A loggte eine WARNING: {warnings}"
    assert progress_calls == [(50, "Rendering 50%...")], (
        f"B-467: gueltiger out_time-Frame erzeugte kein/falsches Update: {progress_calls}"
    )
