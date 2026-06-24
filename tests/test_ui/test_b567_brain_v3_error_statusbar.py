"""B-567 — End-to-End-Beweis der brain_v3-Fehler-Bruecke + Overwrite-Resistenz.

Verifiziert die volle Production-Kette: fehlgeschlagener Embedding-Job
-> EmbeddingScheduler.job_progress (mit error) -> echter Production-Slot
``PBWindow._on_brain_v3_job_progress`` -> ``PBWindow.show_status_error``
-> persistentes Fehler-Label in der Statusleiste.

WICHTIG (live verifiziert 2026-06-24, pb-gui-tester): ``statusBar().showMessage``
allein genuegt NICHT — Routine-Updates („… | System bereit") ueberschreiben den
transienten Banner sofort. Der entscheidende Test ist daher, dass das permanente
Error-Label nach einem konkurrierenden ``showMessage`` WEITERHIN sichtbar bleibt.
"""
from __future__ import annotations

import os
import time
import types
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow  # noqa: E402

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


def _wire_window():
    """Reales QMainWindow mit dem persistenten Error-Label, wie PBWindow es
    aufbaut, und den UNVERAENDERTEN Production-Methoden daran gebunden."""
    from main import PBWindow

    win = QMainWindow()
    win._status_error_label = QLabel("")
    win._status_error_label.hide()
    win.statusBar().addPermanentWidget(win._status_error_label)
    win._status_error_timer = QTimer(win)
    win._status_error_timer.setSingleShot(True)
    win.show_status_error = types.MethodType(PBWindow.show_status_error, win)
    win._clear_status_error = types.MethodType(PBWindow._clear_status_error, win)
    win._status_error_timer.timeout.connect(win._clear_status_error)
    win._on_brain_v3_job_progress = types.MethodType(
        PBWindow._on_brain_v3_job_progress, win
    )
    return win


def test_failed_brain_v3_job_shows_persistent_error(qt_app, isolated_appdata):
    def _raising_embedder(task, progress_cb, serializer):
        raise RuntimeError("defektes Medium 0xDEAD")

    win = _wire_window()
    scheduler = EmbeddingScheduler(
        n_workers=1, embedder_factory=_raising_embedder,
        serializer=GpuSerializer(empty_cache_on_release=False),
    )
    scheduler.job_progress.connect(win._on_brain_v3_job_progress)
    scheduler.start()
    try:
        job_id = scheduler.submit_path(
            media_hash="a" * 64,
            source_path=isolated_appdata / "broken.mp4",
            media_type="video",
        )
        assert job_id is not None

        # isHidden() statt isVisible(): das Top-Level-Fenster wird im Offscreen-
        # Test nie ge-show()-t, daher ist isVisible() der Kinder immer False.
        # isHidden() reflektiert unser explizites show()/hide().
        deadline = time.time() + 5.0
        while time.time() < deadline:
            _spin(qt_app, 50)
            if not win._status_error_label.isHidden() and win._status_error_label.text():
                break

        label = win._status_error_label
        assert not label.isHidden(), "persistentes Error-Label wurde nicht gezeigt"
        assert "Brain-V3-Analyse fehlgeschlagen" in label.text(), f"war: {label.text()!r}"
        assert "defektes Medium 0xDEAD" in label.text(), f"war: {label.text()!r}"

        # KERN-ASSERTION (B-567 live-Bug): ein konkurrierendes Routine-showMessage
        # darf das Fehler-Label NICHT verschlucken.
        win.statusBar().showMessage("3 Datei(en) importiert | System bereit")
        _spin(qt_app, 50)
        assert not label.isHidden(), "Error-Label nach Routine-showMessage verschwunden"
        assert "defektes Medium 0xDEAD" in label.text(), (
            f"Fehler vom Routine-showMessage ueberschrieben, war: {label.text()!r}"
        )
        # Beide koexistieren: temporaere Message + permanentes Label.
        assert "System bereit" in win.statusBar().currentMessage()
    finally:
        scheduler.request_stop(timeout_ms=3000)
        win.deleteLater()


def test_show_status_error_auto_clears(qt_app):
    win = _wire_window()
    try:
        win.show_status_error("Testfehler", timeout_ms=80)
        assert not win._status_error_label.isHidden()
        _spin(qt_app, 250)
        assert win._status_error_label.isHidden(), "Auto-Clear nicht erfolgt"
        assert win._status_error_label.text() == ""
    finally:
        win.deleteLater()
