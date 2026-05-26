"""B-391: FrameExtract-Fehlermeldung darf die Ursache nicht verlieren.

ffmpeg lief mit `-v quiet`, der UI-Fehlertext wurde aber aus stderr gebaut →
bei Fehlern leer → generische Meldung ohne Ursache. Fix: `-v error` (Fehler
landen auf stderr) plus Exitcode-Fallback, falls stderr leer ist.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import subprocess
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from workers.video import FrameExtractWorker


def _qapp():
    return QApplication.instance() or QApplication([])


def test_frame_extract_uses_v_error_not_quiet(monkeypatch):
    _qapp()
    worker = FrameExtractWorker("bad.mp4", 1.0, 2, 2)
    captured = {}

    def fake_run(cmd, *a, **k):
        captured["cmd"] = cmd
        return SimpleNamespace(returncode=1, stdout=b"", stderr=b"boom")

    monkeypatch.setattr(subprocess, "run", fake_run)
    worker.error.connect(lambda m: None)
    worker.run()

    assert "quiet" not in captured["cmd"]
    assert "error" in captured["cmd"]


def test_frame_extract_error_includes_cause_when_stderr_empty(monkeypatch):
    _qapp()
    worker = FrameExtractWorker("bad.mp4", 1.0, 2, 2)

    def fake_run(cmd, *a, **k):
        return SimpleNamespace(returncode=42, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    errors = []
    worker.error.connect(lambda m: errors.append(m))
    worker.run()

    assert errors, "Fehlersignal muss emittiert werden"
    assert "42" in errors[0], "Exitcode-Hinweis muss in der Meldung erscheinen"
