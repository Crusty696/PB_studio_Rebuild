"""B-697: BeatAnalysisService.unload() muss unter GPU_EXECUTION_LOCK laufen.

Der Service ist ein prozessweiter Singleton -> alle Tracks teilen EIN Modell.
Ohne Lock gibt unload() das Modell frei, waehrend ein paralleler Worker noch
darauf inferiert -> NoneType-Call / VRAM-use-after-free (Heap-Corruption,
B-684-Klasse).

Gemessen wird der TEARDOWN-START (der ``cpu()``-Aufruf am Modell, erster
Schritt des Teardowns) — nicht Wall-Clock: der alte Code ruft ``cpu()``
sofort auf, obwohl ein anderer Thread den GPU_EXECUTION_LOCK haelt; der
gefixte Code wartet erst auf den Lock.
"""
import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _FakeModel:
    def __init__(self):
        self.cpu_called = threading.Event()

    def cpu(self):
        self.cpu_called.set()
        return self


def test_unload_teardown_waits_for_gpu_execution_lock():
    # torch VORAB importieren: unload() macht ``import torch`` als ersten
    # Schritt. Ohne Pre-Import misst das 1s-Fenster den sekundenlangen
    # torch-Cold-Import statt des Lock-Wartens -> falsch-gruen auf altem Code.
    import torch  # noqa: F401

    from services.model_manager import GPU_EXECUTION_LOCK
    from services.beat_analysis_service import BeatAnalysisService

    svc = BeatAnalysisService()
    model = _FakeModel()
    svc._model = model

    done = threading.Event()

    def _do_unload():
        svc.unload()
        done.set()

    # Simuliert einen parallelen Worker, der gerade inferiert (haelt den Lock).
    GPU_EXECUTION_LOCK.acquire()
    t = threading.Thread(target=_do_unload, daemon=True)
    try:
        t.start()
        # Kern-Assertion: solange der Lock gehalten wird, darf der Teardown
        # NICHT beginnen. Alter Code ruft cpu() sofort -> Event gesetzt -> RED.
        teardown_started = model.cpu_called.wait(timeout=1.0)
        assert not teardown_started, (
            "unload() begann den Modell-Teardown (cpu()), obwohl ein anderer "
            "Thread den GPU_EXECUTION_LOCK haelt (B-697)"
        )
        assert svc._model is not None
    finally:
        GPU_EXECUTION_LOCK.release()

    # Nach Lock-Freigabe muss der Teardown durchlaufen. Grosszuegig: der erste
    # CUDA-Call (empty_cache) initialisiert lazy den Context (kalt mehrere s).
    assert done.wait(timeout=30.0), "unload() lief nach Lock-Freigabe nicht durch"
    t.join(timeout=5.0)
    assert model.cpu_called.is_set()
    assert svc._model is None


def test_unload_noop_when_other_thread_already_unloaded():
    """Double-Unload-Race: waehrend unload() auf den Lock wartet, hat ein
    anderer Thread bereits entladen -> zweiter unload() ist sauberer No-Op."""
    from services.beat_analysis_service import BeatAnalysisService

    svc = BeatAnalysisService()
    svc._model = None
    svc.unload()  # darf nicht werfen
    assert svc._model is None
