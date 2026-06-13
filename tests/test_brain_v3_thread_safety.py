"""H-12: BrainV3Service.feedback() muss aus parallelen Threads sicher sein.

Vorher: Service-Header dokumentierte "NICHT thread-safe"; parallele
feedback()-Aufrufe auf einer geteilten Instanz verschraenkten die
BEGIN..COMMIT-Transaktion auf der gecachten sqlite3-Connection
("cannot start a transaction within a transaction") bzw. korrumpierten
die Zaehler. Fix: prozessweiter RLock um den Schreibpfad IM Service.

Headless (kein Qt noetig).
"""
from __future__ import annotations

import threading

from services.brain_v3.brain_v3_service import BrainV3Service
from services.brain_v3.cold_start import BRIDGE_AXES
from services.brain_v3.context_resolver import CutContext, context_keys
from services.brain_v3.schemas.brain_v3_schemas import FeedbackRequest
from services.brain_v3.storage.brain_store import BrainStore
from services.brain_v3.weight_store import WeightStore

N_THREADS = 5
N_CALLS_PER_THREAD = 30


def _make_service(tmp_path) -> BrainV3Service:
    store = BrainStore(
        weights_path=tmp_path / "weights.db",
        patterns_path=tmp_path / "patterns.db",
    )
    return BrainV3Service(
        brain_store=store,
        weight_store=WeightStore(store.weights_path),
    )


def test_feedback_parallel_threads_no_exception_no_corruption(tmp_path):
    """5 Threads x 30 feedback()-Calls auf EINER geteilten Instanz."""
    svc = _make_service(tmp_path)
    errors: list[BaseException] = []
    barrier = threading.Barrier(N_THREADS)

    def hammer() -> None:
        try:
            barrier.wait(timeout=10)
            for _ in range(N_CALLS_PER_THREAD):
                resp = svc.feedback(FeedbackRequest(cut_id=1, rating="perfect"))
                assert resp.n_buckets_updated == len(BRIDGE_AXES) * 6
        except BaseException as exc:  # noqa: BLE001 — alles sammeln
            errors.append(exc)

    threads = [threading.Thread(target=hammer) for _ in range(N_THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert not errors, f"Parallele feedback()-Calls warfen: {errors!r}"

    # Korruptions-Check: 'perfect' = alpha+=2.0 pro Bucket. Erwartet pro
    # Achse/Level exakt N_THREADS * N_CALLS * 2.0 — kein Lost Update.
    expected_alpha = N_THREADS * N_CALLS_PER_THREAD * 2.0
    keys_by_level = context_keys(CutContext())
    ws = WeightStore(tmp_path / "weights.db")
    try:
        for axis in BRIDGE_AXES:
            for level, key in enumerate(keys_by_level):
                ab = ws.get_alpha_beta(axis, level, key)
                assert ab is not None, f"Bucket fehlt: {axis}/{level}/{key}"
                assert ab.alpha == expected_alpha, (
                    f"Lost Update {axis}/{level}: {ab.alpha} != {expected_alpha}"
                )
                assert ab.beta == 0.0
    finally:
        ws.close()


def test_feedback_parallel_threads_separate_instances(tmp_path):
    """Wie der Popup-Worker: pro Thread eine eigene Service-Instanz,
    alle auf derselben weights.db."""
    store = BrainStore(
        weights_path=tmp_path / "weights.db",
        patterns_path=tmp_path / "patterns.db",
    )
    errors: list[BaseException] = []
    barrier = threading.Barrier(N_THREADS)

    def hammer() -> None:
        svc = BrainV3Service(
            brain_store=store,
            weight_store=WeightStore(store.weights_path),
        )
        try:
            barrier.wait(timeout=10)
            for _ in range(N_CALLS_PER_THREAD):
                svc.feedback(FeedbackRequest(cut_id=2, rating="no_match"))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            svc._weight_store.close()

    threads = [threading.Thread(target=hammer) for _ in range(N_THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert not errors, f"Parallele feedback()-Calls warfen: {errors!r}"

    expected_beta = N_THREADS * N_CALLS_PER_THREAD * 2.0
    keys_by_level = context_keys(CutContext())
    ws = WeightStore(tmp_path / "weights.db")
    try:
        ab = ws.get_alpha_beta(BRIDGE_AXES[0], 0, keys_by_level[0])
        assert ab is not None
        assert ab.beta == expected_beta
    finally:
        ws.close()
