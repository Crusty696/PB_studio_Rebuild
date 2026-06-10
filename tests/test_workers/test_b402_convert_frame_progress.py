"""B-402: Batch-Convert soll echten FFmpeg-Frame-Fortschritt melden.

Vorher emittierte BatchConvertWorker nur Item-Count-Sprünge
(int((i+1)/total*100)). Fix: -progress pipe:1 + out_time_ms-Parsing im
Runner liefert die Ausgabe-Zeit (Sekunden) pro Clip an einen progress_cb.
"""

from __future__ import annotations

import inspect
import time
from unittest.mock import patch

import workers.import_export as ie


class _FakePopen:
    def __init__(self, stdout_lines):
        self.stdout = iter(stdout_lines)

        class _Err:
            def read(self_inner):
                return b""
        self.stderr = _Err()
        self.returncode = 0
        self._polls = 0

    def poll(self):
        # Erst ein paar Runden "laeuft noch" (None), damit der Reader-Thread
        # out_time_ms lesen + der Loop emittieren kann, dann beendet (0).
        self._polls += 1
        return None if self._polls < 6 else 0

    def terminate(self):
        pass

    def kill(self):
        pass

    def wait(self, timeout=None):
        return 0


def test_b402_runner_emits_out_time_progress():
    captured = []
    fake = _FakePopen([b"out_time_ms=N/A\n", b"out_time_ms=5000000\n",
                       b"progress=continue\n"])
    with patch.object(ie.subprocess, "Popen", return_value=fake):
        result = ie._run_batch_ffmpeg_cancellable(
            ["ffmpeg", "-progress", "pipe:1", "out.mp4"],
            cancel_check=lambda: False,
            timeout=10,
            progress_cb=lambda sec: captured.append(sec),
        )
    assert result.returncode == 0
    assert 5.0 in captured, f"erwartete out_time 5.0s im Progress, war {captured}"
    # N/A darf NICHT als 0-Sprung-Zahl reinkommen (wird uebersprungen)
    assert all(isinstance(s, float) for s in captured)


def test_b402_runner_without_cb_uses_communicate(monkeypatch):
    """Ohne progress_cb bleibt der alte Pfad (communicate) erhalten."""
    class _P:
        def __init__(self):
            self._n = 0
            self.returncode = 0
        def poll(self):
            self._n += 1
            return None if self._n < 2 else 0
        def communicate(self, timeout=None):
            return (b"", b"")
    with patch.object(ie.subprocess, "Popen", return_value=_P()):
        result = ie._run_batch_ffmpeg_cancellable(
            ["ffmpeg", "out.mp4"], cancel_check=lambda: False, timeout=10,
        )
    assert result.returncode == 0


def test_b402_convert_cmd_has_progress_flag():
    src = inspect.getsource(ie.BatchConvertWorker)
    assert '"-progress", "pipe:1"' in src
    assert "progress_cb=" in src
    assert "_ffprobe_duration" in src
