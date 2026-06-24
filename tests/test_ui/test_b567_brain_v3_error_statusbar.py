"""B-567 Rest — End-to-End-Beweis der brain_v3-Fehler-Bruecke.

Verifiziert die VOLLE Production-Kette ohne Mock des kritischen Pfads:
fehlgeschlagener Embedding-Job -> EmbeddingScheduler.job_progress (mit error)
-> echter Production-Slot ``PBWindow._on_brain_v3_job_progress`` -> rote
``statusBar().showMessage`` an einem realen QMainWindow.

Der Unit-Test ``test_failed_job_emits_error_text`` deckt nur Signal->error ab.
Hier wird der in ``main.py`` verdrahtete Slot 1:1 ausgefuehrt (gleiche Bindung
wie ``scheduler.job_progress.connect(self._on_brain_v3_job_progress)``), damit
auch Slot->Statusleiste live bewiesen ist.
"""
from __future__ import annotations

import os
import time
import types
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMainWindow  # noqa: E402

from services.brain_v3.embedding_scheduler import (  # noqa: E402
    EmbeddingScheduler,
    reset_default_scheduler_for_tests,
)
from services.brain_v3.gpu_serializer import (  # noqa: E402
    GpuSerializer,
    reset_default_serializer_for_tests,
)


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def isolated_appdata(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    reset_default_serializer_for_tests()
    reset_default_scheduler_for_tests()
    yield tmp_path
    reset_default_scheduler_for_tests()
    reset_default_serializer_for_tests()


def _spin(app, ms: int = 100) -> None:
    deadline = time.time() + ms / 1000.0
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.005)


def test_failed_brain_v3_job_shows_red_statusbar(qt_app, isolated_appdata):
    from main import PBWindow

    def _raising_embedder(task, progress_cb, serializer):
        raise RuntimeError("defektes Medium 0xDEAD")

    win = QMainWindow()
    # Exakte Bindung wie in main.py: der unveraenderte Production-Slot, an ein
    # reales Fenster mit echter Statusleiste gebunden.
    slot = types.MethodType(PBWindow._on_brain_v3_job_progress, win)

    scheduler = EmbeddingScheduler(
        n_workers=1, embedder_factory=_raising_embedder,
        serializer=GpuSerializer(empty_cache_on_release=False),
    )
    scheduler.job_progress.connect(slot)
    scheduler.start()
    try:
        job_id = scheduler.submit_path(
            media_hash="a" * 64,
            source_path=isolated_appdata / "broken.mp4",
            media_type="video",
        )
        assert job_id is not None

        deadline = time.time() + 5.0
        msg = ""
        while time.time() < deadline:
            _spin(qt_app, 50)
            msg = win.statusBar().currentMessage()
            if msg:
                break

        assert msg, "Statusleiste blieb leer — Fehler-Bruecke nicht ausgeloest"
        assert "Brain-V3-Analyse fehlgeschlagen" in msg, f"war: {msg!r}"
        assert "defektes Medium 0xDEAD" in msg, (
            f"Fehlertext nicht in Statuszeile, war: {msg!r}"
        )
    finally:
        scheduler.request_stop(timeout_ms=3000)
        win.deleteLater()
