"""B-627: EmbeddingScheduler-Einreichung darf den aufrufenden (GUI-)Thread
NICHT mehr bis 5s blockieren.

Zwei Regressions-Guards:
1. Fire-and-forget: submit_task() reiht die Job-Coroutine ein und wartet NICHT
   auf deren Ergebnis (frueher future.result(timeout=5.0)). Auch wenn die
   eingereihte Coroutine lange laeuft, kehrt submit_task sofort zurueck.
2. Early submit: trifft ein submit_task ein, bevor der Scheduler-Loop bereit
   ist, crasht das NICHT — der Task wird gepuffert und eine job_id sofort
   zurueckgeliefert.

Deterministisch (keine sleep-Races): Guard 1 macht die eingereihte Coroutine
kuenstlich langsam (3s) und prueft, dass submit_task selbst << 1s braucht.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

import numpy as np
import pytest

from PySide6.QtWidgets import QApplication

from services.brain.embedding_scheduler import (
    EmbeddingTask,
    _SchedulerThread,
    reset_default_scheduler_for_tests,
)
from services.brain.gpu_serializer import (
    GpuSerializer,
    reset_default_serializer_for_tests,
)
from services.brain.storage.embedding_cache import EmbeddingCache


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


def _fake_embedder(task, progress_cb, serializer):
    progress_cb(0.5, "fake")
    return {
        "embedding": np.zeros(8, dtype=np.float32),
        "model_name": "fake/model",
        "model_version": "0.0",
    }


def _make_thread() -> _SchedulerThread:
    return _SchedulerThread(
        n_workers=1,
        cache=EmbeddingCache(),
        embedder_factory=_fake_embedder,
        serializer=GpuSerializer(empty_cache_on_release=False),
    )


def test_b627_early_submit_before_ready_does_not_block_or_crash(
    qt_app, isolated_appdata
):
    """Early submit vor Loop-Ready: kein Crash, sofortige job_id, gepuffert."""
    thread = _make_thread()
    # Thread NICHT gestartet -> _ready False, _loop None (Ready-Fenster simuliert)
    task = EmbeddingTask(
        media_hash="a" * 64, media_type="audio", source_path=Path("x.wav")
    )

    t0 = time.perf_counter()
    job_id = thread.submit_task(task)  # darf nicht raisen
    elapsed = time.perf_counter() - t0

    assert elapsed < 1.0, f"early submit blockierte {elapsed:.2f}s (soll << 5s)"
    assert isinstance(job_id, str) and job_id, "keine gueltige job_id geliefert"
    assert thread._pending, "Task wurde nicht gepuffert"
    assert thread._pending[0][0] == job_id


def test_b627_submit_does_not_wait_for_job_result(qt_app, isolated_appdata):
    """Loop bereit + langsame eingereihte Coroutine: submit_task kehrt sofort
    zurueck (fire-and-forget), wartet NICHT auf das Ergebnis."""
    thread = _make_thread()
    thread.start()
    try:
        assert thread._ready_event.wait(timeout=5.0), "Scheduler-Loop nicht bereit"

        async def _slow(task, job_id):
            await asyncio.sleep(3.0)  # kuenstlich langsame Einreih-Coroutine
            return job_id

        # Bound-Method durch langsame Coroutine ersetzen (Signatur: task, job_id)
        thread._build_and_submit_job = _slow

        task = EmbeddingTask(
            media_hash="b" * 64, media_type="audio", source_path=Path("y.wav")
        )
        t0 = time.perf_counter()
        job_id = thread.submit_task(task)
        elapsed = time.perf_counter() - t0

        assert elapsed < 1.0, (
            f"submit_task blockierte {elapsed:.2f}s — wartet noch auf das "
            "Job-Ergebnis (frueher future.result(5s))"
        )
        assert isinstance(job_id, str) and job_id
    finally:
        thread.request_stop()
        thread.wait(3000)
