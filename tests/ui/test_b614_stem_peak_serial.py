"""B-614: Peak-Jobs laufen SERIELL — maximal ein aktiver Reader.

Vorher starteten 4 parallele QThreads gleichzeitig soundfile-Reads von
derselben Platte (Seek-Konkurrenz + GIL-Druck => Cold-Start-Freezes,
Watchdog-Beweis workspace_switch_perf Lauf 3+4).
"""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, Signal


class _FakePeakWorker(QObject):
    """Ersatz fuer PeakWorker: registriert Parallelitaet, emitted sofort."""

    finished = Signal(str, object)
    error = Signal(str, str)

    active = 0
    max_active = 0
    runs: list[str] = []

    def __init__(self, stem_name: str, file_path: str, target_peaks: int = 8000):
        super().__init__()
        self._stem_name = stem_name

    def cancel(self):
        pass

    def run(self):
        cls = _FakePeakWorker
        cls.active += 1
        cls.max_active = max(cls.max_active, cls.active)
        cls.runs.append(self._stem_name)
        time.sleep(0.05)  # haelt den Slot kurz besetzt -> Parallelitaet messbar
        cls.active -= 1
        self.finished.emit(self._stem_name, np.zeros((0, 2), dtype=np.float32))


def test_b614_peak_jobs_run_serially(qapp, monkeypatch, tmp_path: Path) -> None:
    import ui.widgets.stem_workspace as sw_mod
    from ui.widgets.stem_workspace import StemWorkspace

    monkeypatch.setattr(sw_mod, "PeakWorker", _FakePeakWorker)
    _FakePeakWorker.active = 0
    _FakePeakWorker.max_active = 0
    _FakePeakWorker.runs = []

    paths = {}
    for name in ("vocals", "drums", "bass", "other"):
        p = tmp_path / f"{name}.wav"
        p.write_bytes(b"fake")
        paths[name] = str(p)

    workspace = StemWorkspace()
    try:
        workspace.update_for_track(7, paths)

        # Sofort nach dem Start: genau 1 Job aktiv, Rest wartet in der Queue.
        assert len(workspace._peak_threads) == 1
        assert len(workspace._peak_queue) == 3

        deadline = time.time() + 10.0
        while time.time() < deadline and len(_FakePeakWorker.runs) < 4:
            qapp.processEvents()
            time.sleep(0.02)

        assert sorted(_FakePeakWorker.runs) == ["bass", "drums", "other", "vocals"]
        assert _FakePeakWorker.max_active == 1, (
            f"B-614: {_FakePeakWorker.max_active} Peak-Reader liefen parallel"
        )

        # Queue leer, kein aktiver Job mehr haengen geblieben.
        deadline = time.time() + 5.0
        while time.time() < deadline and (workspace._peak_queue or workspace._peak_active):
            qapp.processEvents()
            time.sleep(0.02)
        assert workspace._peak_queue == []
        assert workspace._peak_active is False
    finally:
        workspace.deleteLater()
        qapp.processEvents()


def test_b614_track_switch_drops_queued_jobs(qapp, monkeypatch, tmp_path: Path) -> None:
    import ui.widgets.stem_workspace as sw_mod
    from ui.widgets.stem_workspace import StemWorkspace

    monkeypatch.setattr(sw_mod, "PeakWorker", _FakePeakWorker)
    _FakePeakWorker.active = 0
    _FakePeakWorker.max_active = 0
    _FakePeakWorker.runs = []

    paths = {}
    for name in ("vocals", "drums", "bass", "other"):
        p = tmp_path / f"{name}.wav"
        p.write_bytes(b"fake")
        paths[name] = str(p)

    workspace = StemWorkspace()
    try:
        workspace.update_for_track(1, paths)
        assert len(workspace._peak_queue) == 3
        # Track-Wechsel (None) -> wartende Jobs des alten Tracks verworfen.
        workspace.update_for_track(None, None)
        assert workspace._peak_queue == []
    finally:
        workspace.deleteLater()
        qapp.processEvents()
