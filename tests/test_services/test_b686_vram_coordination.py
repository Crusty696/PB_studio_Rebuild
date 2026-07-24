"""B-686: VRAM-Koordination ModelManager <-> Brain-V3-Embedding-Scheduler.

Variante C: Embedder-Free am Analyse-run()-Start (vor jeder GPU-Lease) +
Pause/Resume-Gate im Scheduler. Getestet werden:
- Gate-Mechanik (pause/resume, stop-Vorrang, blockieren bis resume),
- pause_for_analysis gibt BEIDE Embedder frei,
- Gate verzoegert echte Embeds bis resume,
- Deadlock-Sicherheit des Lock-Orderings (scharfer Stress-Test mit
  bewusst-falschem Kontroll-Lauf, der deadlocken MUSS).
"""
from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

import services.brain.embedding_scheduler as sched_mod
from services.brain.embedding_scheduler import (
    EmbeddingScheduler,
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


def _make_thread(factory) -> _SchedulerThread:
    return _SchedulerThread(
        n_workers=1,
        cache=EmbeddingCache(),
        embedder_factory=factory,
        serializer=GpuSerializer(empty_cache_on_release=False),
    )


# ── Gate-Mechanik (unit, deterministisch) ─────────────────────────────────

def test_pause_resume_toggles_gate(isolated_appdata):
    thread = _make_thread(lambda *a: None)
    assert not thread._pause_event.is_set()
    thread.pause_embeddings()
    assert thread._pause_event.is_set()
    thread.resume_embeddings()
    assert not thread._pause_event.is_set()


def test_await_gate_stop_has_priority(isolated_appdata):
    thread = _make_thread(lambda *a: None)
    thread.pause_embeddings()
    thread._stop_event.set()  # Stop trotz Pause
    # Stop-Vorrang: _await_gate kehrt sofort mit False zurueck (nicht blockieren).
    result = asyncio.run(asyncio.wait_for(thread._await_gate(), timeout=2.0))
    assert result is False


def test_await_gate_blocks_until_resume(isolated_appdata):
    thread = _make_thread(lambda *a: None)
    thread.pause_embeddings()

    async def _drive():
        gate = asyncio.ensure_future(thread._await_gate())
        await asyncio.sleep(0.3)
        assert not gate.done(), "Gate darf waehrend Pause nicht durchlaufen"
        thread.resume_embeddings()
        return await asyncio.wait_for(gate, timeout=2.0)

    assert asyncio.run(_drive()) is True


def test_nested_pause_gate_stays_closed_until_all_resume(isolated_appdata):
    """P1-Fix: zwei parallele Analyse-Worker (2x pause). Ein resume darf das
    Gate NICHT oeffnen, solange der zweite Worker noch pausiert haelt."""
    thread = _make_thread(lambda *a: None)

    thread.pause_embeddings()   # Worker A
    thread.pause_embeddings()   # Worker B
    assert thread._pause_event.is_set()

    thread.resume_embeddings()  # A fertig
    assert thread._pause_event.is_set(), (
        "Gate darf nicht aufgehen, solange Worker B noch pausiert (P1)"
    )

    thread.resume_embeddings()  # B fertig
    assert not thread._pause_event.is_set(), "nach dem letzten resume Gate offen"


def test_resume_underflow_is_safe(isolated_appdata):
    """resume ohne vorheriges pause darf den Zaehler nicht negativ machen."""
    thread = _make_thread(lambda *a: None)
    thread.resume_embeddings()
    thread.resume_embeddings()
    assert thread._pause_count == 0
    assert not thread._pause_event.is_set()


def test_worker_pause_is_before_any_gpu_lease():
    """Regressions-Anker (P2): in beiden Worker-run() muss der Pause-Aufruf VOR
    der ersten GPU-Lease stehen. Verschoebe jemand die Pause unter eine
    gpu_resource_lease/gpu_execution_lease, entstuende die verbotene
    LOAD->EXECUTION-Inversion (Deadlock) — das faengt dieser Test statisch."""
    import inspect

    from workers.video import VideoAnalysisPipelineWorker, VideoBatchAnalysisWorker

    for worker_cls in (VideoAnalysisPipelineWorker, VideoBatchAnalysisWorker):
        src = inspect.getsource(worker_cls.run)
        pause_pos = src.find("_pause_embeddings_for_analysis()")
        assert pause_pos != -1, f"{worker_cls.__name__}: kein Pause-Aufruf"
        for lease in ("gpu_resource_lease", "gpu_execution_lease", "acquire("):
            lease_pos = src.find(lease)
            if lease_pos != -1:
                assert pause_pos < lease_pos, (
                    f"{worker_cls.__name__}: Pause ({pause_pos}) liegt NACH "
                    f"'{lease}' ({lease_pos}) — Deadlock-Gefahr (B-686)"
                )


# ── pause_for_analysis gibt beide Embedder frei ───────────────────────────

def test_pause_for_analysis_unloads_both_embedders(isolated_appdata, monkeypatch):
    unloaded = []

    class _FakeEmb:
        def __init__(self, name):
            self.name = name

        def unload(self):
            unloaded.append(self.name)

    monkeypatch.setattr(sched_mod, "_VIDEO_EMBEDDER", _FakeEmb("video"))
    monkeypatch.setattr(sched_mod, "_AUDIO_EMBEDDER", _FakeEmb("audio"))

    scheduler = EmbeddingScheduler()  # kein Thread -> nur Free-Pfad
    scheduler.pause_for_analysis()

    assert set(unloaded) == {"video", "audio"}, "beide Embedder muessen entladen werden"
    # Globals danach zurueckgesetzt (naechster Job laedt lazy neu).
    assert sched_mod._VIDEO_EMBEDDER is None
    assert sched_mod._AUDIO_EMBEDDER is None


# ── Gate verzoegert echte Embeds bis resume (integration) ─────────────────

def test_gate_defers_embed_until_resume(qt_app, isolated_appdata):
    calls = []

    def _recording_factory(task, progress_cb, serializer):
        calls.append(task.media_hash)
        progress_cb(0.5, "fake")
        return {
            "embedding": np.zeros(8, dtype=np.float32),
            "model_name": "fake/model",
            "model_version": "0.0",
        }

    scheduler = EmbeddingScheduler(embedder_factory=_recording_factory)
    scheduler.start()
    assert scheduler._thread.wait_ready(timeout=5.0)

    scheduler._thread.pause_embeddings()  # Gate zu (ohne Free — nur Gate testen)
    scheduler.submit_path("b" * 64, Path("x.mp4"), "video")

    time.sleep(0.6)  # Gate haelt den Job -> Factory NICHT gerufen
    assert calls == [], "pausierter Embed darf die Factory nicht erreichen"

    scheduler._thread.resume_embeddings()
    deadline = time.monotonic() + 5.0
    while not calls and time.monotonic() < deadline:
        time.sleep(0.05)
    assert calls == ["b" * 64], "nach resume muss der Embed laufen"

    scheduler.request_stop(timeout_ms=5000)


# ── Deadlock-Sicherheit: scharfer Stress-Test ─────────────────────────────
#
# Modelliert die reale Lock-Falle mit ISOLIERTEN Locks (keine globalen
# GPU-Locks -> keine Suite-Vergiftung falls der Kontroll-Lauf deadlockt):
#  - load_lock  ~ GPU_LOAD_LOCK
#  - exec_lock  ~ GPU_EXECUTION_LOCK (der GpuSerializer bridged darauf)
#  - Embed-Thread: exec -> load  (oom_recovery-Muster: haelt EXECUTION, nimmt LOAD)
#  - SAFE Worker:  exec (Free, released) DANN load-Lease  -> nie load gehalten
#                  waehrend exec angefordert wird -> keine Inversion
#  - BAD  Worker:  load DANN exec (Free INNERHALB der Load-Lease) -> Inversion

def test_safe_ordering_does_not_deadlock():
    """SAFE: Free (EXEC) VOR der Load-Lease, EXEC dabei nie gehalten waehrend
    LOAD angefordert wird. Muss durchlaufen. Viele Iterationen als Stress."""
    load_lock = threading.RLock()
    exec_lock = threading.RLock()
    start = threading.Barrier(2)
    err = []
    iterations = 40

    def _worker():
        try:
            for _ in range(iterations):
                start.wait()
                with exec_lock:      # Free: EXEC, sofort released
                    pass
                with load_lock:      # dann Load-Lease (kein EXEC gehalten)
                    pass
        except BaseException as e:  # noqa: BLE001
            err.append(e)

    def _embedder():
        try:
            for _ in range(iterations):
                start.wait()
                with exec_lock:      # haelt EXEC ...
                    with load_lock:  # ... und will LOAD (oom_recovery-Muster)
                        pass
        except BaseException as e:  # noqa: BLE001
            err.append(e)

    tw = threading.Thread(target=_worker, daemon=True)
    te = threading.Thread(target=_embedder, daemon=True)
    tw.start(); te.start()
    tw.join(15.0); te.join(5.0)
    assert not err, f"Fehler im sicheren Lauf: {err}"
    assert not tw.is_alive() and not te.is_alive(), (
        "sicheres Ordering (Free vor Lease) darf NICHT deadlocken"
    )


def test_control_bad_ordering_deadlocks():
    """Schaerfe-Nachweis: das verbotene Ordering (Free INNERHALB der Load-Lease)
    MUSS deadlocken — sonst wuerde der Safe-Test nichts beweisen.

    Mid-Barrier erzwingt das Interleaving: beide Threads halten ihren ERSTEN
    Lock, bevor sie den zweiten anfordern -> garantierte Inversion. Isolierte
    Locks -> keine Vergiftung anderer Tests; Daemon-Threads leaken bounded."""
    load_lock = threading.Lock()
    exec_lock = threading.Lock()
    start = threading.Barrier(2)
    mid = threading.Barrier(2)

    def _bad_worker():
        try:
            start.wait()
            with load_lock:          # haelt LOAD
                mid.wait()           # warten bis embedder EXEC haelt
                with exec_lock:      # will EXEC (embedder haelt es) -> Deadlock
                    pass
        except BaseException:  # noqa: BLE001
            pass

    def _bad_embedder():
        try:
            start.wait()
            with exec_lock:          # haelt EXEC
                mid.wait()           # warten bis worker LOAD haelt
                with load_lock:      # will LOAD (worker haelt es) -> Deadlock
                    pass
        except BaseException:  # noqa: BLE001
            pass

    tw = threading.Thread(target=_bad_worker, daemon=True)
    te = threading.Thread(target=_bad_embedder, daemon=True)
    tw.start(); te.start()
    tw.join(6.0); te.join(2.0)
    assert tw.is_alive() and te.is_alive(), (
        "Kontroll-Lauf (LOAD->EXEC-Inversion) haette deadlocken muessen — "
        "der Stress-Test ist sonst nicht scharf"
    )
