"""B-774: CUDA-Kontextverlust unter Dauerlast darf die Batch-Analyse nicht
65x kaskadieren lassen.

Real-Log 2026-08-08: ``RuntimeError: CUDA error: unknown error`` bei Clip
302/364 — der per-Clip-Skip (C-04) behandelte den Kontexttod als Einzelfehler,
alle 65 Folge-Clips crashten sofort mit demselben Fehler gegen den toten
Kontext. Fix: ``_is_cuda_context_error``-Heuristik (OOM ausgenommen) +
``ModelManager().cuda_health_check()`` als Autoritaet + 2-in-Folge-Zaehler;
bei Kontexttod ``CudaContextLostError`` -> Batch-Stopp mit genau EINEM
error-Emit (Neustart-Meldung) und genau EINEM finished-Emit.

Kein GPU/Qt-Thread noetig: ``run()`` laeuft synchron, Signale direkt
verbunden, ``run_full_pipeline`` gemonkeypatcht (Muster
test_b674_video_batch_ffmpegerror_isolation.py).
"""

import contextlib

from workers import video as vmod

_RESTART_MSG_PARTS = ("CUDA-Kontext verloren", "App neu starten")


@contextlib.contextmanager
def _noop_lease(*_a, **_k):
    yield


def _install_stubs(monkeypatch, health_results):
    """ModelManager/Leases/Warmup/VideoAnalyzer stubben — kein CUDA, kein Download.

    ``health_results``: Queue der cuda_health_check()-Antworten (danach True).
    Rueckgabe: state-dict mit ``health_calls`` und ``ctx_lost``-Zaehlern.
    """
    import services.model_manager as mm_mod
    import services.model_warmup as warmup_mod

    state = {"health_calls": 0, "ctx_lost": 0}

    class _FakeMM:
        device = "cuda"
        model_type = "siglip"

        def load_siglip(self):
            # -> Worker-Fallback "pro Video laden", Batch-Referenz bleibt None.
            raise RuntimeError("kein SigLIP im Test")

        def load_raft(self):
            return (None, None)

        def unload(self):
            pass

        def cuda_health_check(self):
            state["health_calls"] += 1
            if health_results:
                return health_results.pop(0)
            return True

        def mark_cuda_context_lost(self):
            state["ctx_lost"] += 1

        def notify_power_resume(self):
            state["ctx_lost"] += 1

    monkeypatch.setattr(mm_mod, "ModelManager", _FakeMM)
    monkeypatch.setattr(mm_mod, "gpu_resource_lease", _noop_lease)
    monkeypatch.setattr(mm_mod, "gpu_execution_lease", _noop_lease)
    # B-222 Pre-Flight darf im Test keinen 2.5-GB-Download anstossen.
    monkeypatch.setattr(warmup_mod, "is_siglip_cached", lambda: (True, []))

    class _FakeAnalyzer:
        def analyze_and_store(self, clip_id, create_proxy=False, **_kw):
            return None

    monkeypatch.setattr(vmod, "VideoAnalyzer", _FakeAnalyzer)
    return state


def _run_worker(monkeypatch, fail_map, health_results):
    """3-Clip-Batch synchron laufen lassen.

    ``fail_map``: clip_id -> Exception, die run_full_pipeline werfen soll.
    """
    import services.video_analysis_service as vas_mod

    state = _install_stubs(monkeypatch, health_results)
    calls = []

    def fake_pipeline(*, video_path, video_clip_id, **_kw):
        calls.append(video_clip_id)
        exc = fail_map.get(video_clip_id)
        if exc is not None:
            raise exc
        return vas_mod.PipelineResult(
            video_path=video_path, scenes=[], embeddings_stored=0
        )

    monkeypatch.setattr(vas_mod, "run_full_pipeline", fake_pipeline)

    batch = [(1, "x/a.mp4", "A"), (2, "x/b.mp4", "B"), (3, "x/c.mp4", "C")]
    worker = vmod.VideoAnalysisPipelineWorker(batch=batch)
    finished, errors = [], []
    worker.finished.connect(lambda cid, d: finished.append((cid, d)))
    worker.error.connect(lambda cid, msg: errors.append((cid, msg)))

    worker.run()
    return calls, finished, errors, state, worker


def _cuda_dead_exc():
    return RuntimeError("CUDA error: unknown error")


def test_probe_dead_stops_after_first_cuda_failure(monkeypatch, qtbot):
    """(a) Health-Probe False -> Batch stoppt nach EINEM Fehl-Clip."""
    calls, finished, errors, state, worker = _run_worker(
        monkeypatch, {1: _cuda_dead_exc()}, health_results=[False],
    )
    assert calls == [1], "Folge-Clips duerfen NICHT mehr versucht werden"
    assert len(errors) == 1, "genau EIN error-Emit (keine 65x-Kaskade)"
    for part in _RESTART_MSG_PARTS:
        assert part in errors[0][1], f"Neustart-Meldung muss '{part}' enthalten"
    assert len(finished) == 1, "genau EIN finished-Emit (thread.quit-Vertrag)"
    assert state["ctx_lost"] == 1, "ModelManager muss Kontexttod signalisiert bekommen"
    assert worker._errored is True


def test_probe_alive_two_consecutive_cuda_failures_stop(monkeypatch, qtbot):
    """(b) Probe luegt True, aber 2 CUDA-Fehler in Folge -> Stopp."""
    calls, finished, errors, state, worker = _run_worker(
        monkeypatch,
        {1: _cuda_dead_exc(), 2: _cuda_dead_exc()},
        health_results=[True, True],
    )
    assert calls == [1, 2], "nach dem 2. CUDA-Fehler in Folge ist Schluss"
    assert len(errors) == 1
    assert len(finished) == 1
    assert state["health_calls"] == 2
    assert state["ctx_lost"] == 1
    assert worker._errored is True


def test_success_between_cuda_failures_resets_counter(monkeypatch, qtbot):
    """(c) Erfolgs-Clip dazwischen resettet den Zaehler -> kein Batch-Stopp."""
    calls, finished, errors, state, worker = _run_worker(
        monkeypatch,
        {1: _cuda_dead_exc(), 3: _cuda_dead_exc()},
        health_results=[True, True],
    )
    assert calls == [1, 2, 3], "alle Clips muessen versucht werden"
    assert errors == [], "kein batch-fataler error"
    assert len(finished) == 1
    assert state["ctx_lost"] == 0
    assert worker._errored is False


def test_cuda_oom_stays_per_clip_isolated(monkeypatch, qtbot):
    """(d) 'CUDA out of memory' ist KEIN Kontexttod -> bestehender Skip-Pfad."""
    oom = RuntimeError(
        "CUDA out of memory. Tried to allocate 512.00 MiB (GPU 0; 6.00 GiB total)"
    )
    calls, finished, errors, state, worker = _run_worker(
        monkeypatch, {2: oom}, health_results=[],
    )
    assert calls == [1, 2, 3], "OOM-Clip wird uebersprungen, Batch laeuft weiter"
    assert errors == []
    assert len(finished) == 1
    assert state["health_calls"] == 0, "fuer OOM darf keine CUDA-Probe laufen"
    assert state["ctx_lost"] == 0
    assert worker._errored is False


def test_is_cuda_context_error_heuristic():
    """Marker-Strings matchen, OOM + fremde Typen nicht."""
    assert vmod._is_cuda_context_error(RuntimeError("CUDA error: unknown error"))
    assert vmod._is_cuda_context_error(RuntimeError("an illegal memory access was encountered"))
    assert vmod._is_cuda_context_error(RuntimeError("CUBLAS_STATUS_EXECUTION_FAILED"))
    assert vmod._is_cuda_context_error(RuntimeError("unspecified launch failure"))
    assert not vmod._is_cuda_context_error(RuntimeError("CUDA out of memory. Tried to allocate"))
    assert not vmod._is_cuda_context_error(ValueError("CUDA error: unknown error"))
    assert not vmod._is_cuda_context_error(RuntimeError("Datei kaputt"))
