"""B-143 hardening refactor: ``track_lock`` ContextManager.

Folge-Risiko nach dem Refcount-Fix von B-143: Caller muessen
``_get_track_lock`` und ``_release_track_lock`` korrekt paarweise im
finally aufrufen — vergisst ein zukuenftiger Caller das ``release``,
leakt der Refcount und der Eintrag persistiert auf ewig.

Hardening: ``track_lock(track_id)`` ContextManager, der
acquire+release atomar kapselt:

    with track_lock(track_id):
        ...

Auch bei Exception innerhalb des Blocks muss der Refcount sauber
auf den Vorher-Stand zurueckgehen.
"""

from __future__ import annotations

import inspect
import threading

import pytest

from services import audio_service


def _refs_snapshot() -> dict[int, int]:
    with audio_service._track_locks_guard:
        return dict(audio_service._track_lock_refs)


def test_track_lock_is_a_context_manager_decorator_or_class() -> None:
    """``track_lock`` muss als ``with``-faehiger ContextManager exportiert
    werden — entweder ueber ``@contextmanager`` oder Klasse mit
    ``__enter__``/``__exit__``."""
    assert hasattr(audio_service, "track_lock"), (
        "B-143 hardening: ``track_lock`` ContextManager fehlt in "
        "services.audio_service."
    )
    cm_factory = audio_service.track_lock
    cm = cm_factory(999_999)
    assert hasattr(cm, "__enter__") and hasattr(cm, "__exit__"), (
        "``track_lock(track_id)`` muss ein ContextManager sein "
        "(``__enter__``/``__exit__``)."
    )
    # Cleanup nach dem reinen Probe-Aufruf (ohne with-Statement) —
    # @contextmanager-Generator hat noch nicht gestartet, also kein
    # Refcount-Effekt erwartet.


def test_track_lock_releases_refcount_on_normal_exit() -> None:
    """Bei normalem Block-Exit muss der Refcount auf 0 zurueckgehen
    und der Eintrag aus _track_locks/_track_lock_refs entfernt sein."""
    track_id = 424_242
    before = _refs_snapshot()
    with audio_service.track_lock(track_id):
        # Innerhalb: Eintrag existiert mit refcount==1
        with audio_service._track_locks_guard:
            assert audio_service._track_lock_refs.get(track_id) == 1
            assert track_id in audio_service._track_locks
    # Nach Block: Eintrag wieder weg
    after = _refs_snapshot()
    assert after == before, (
        f"track_lock leakte Refcount-Eintrag fuer track {track_id}: "
        f"vorher={before}, nachher={after}"
    )
    with audio_service._track_locks_guard:
        assert track_id not in audio_service._track_locks


def test_track_lock_releases_refcount_on_exception() -> None:
    """KERNTEST: bei Exception innerhalb des with-Blocks muss der
    Refcount-Cleanup trotzdem sauber laufen — sonst ist der
    ContextManager wertlos gegenueber dem manuellen Pattern."""
    track_id = 424_243
    before = _refs_snapshot()
    with pytest.raises(RuntimeError, match="boom"):
        with audio_service.track_lock(track_id):
            with audio_service._track_locks_guard:
                assert audio_service._track_lock_refs.get(track_id) == 1
            raise RuntimeError("boom")
    after = _refs_snapshot()
    assert after == before, (
        f"track_lock leakte Refcount nach Exception: vorher={before}, "
        f"nachher={after}"
    )
    with audio_service._track_locks_guard:
        assert track_id not in audio_service._track_locks
        assert track_id not in audio_service._track_lock_refs


def test_track_lock_serializes_concurrent_callers_for_same_id() -> None:
    """Zwei Threads im ``with track_lock(5):``-Block duerfen NICHT
    gleichzeitig Critical-Section-Code laufen lassen — gleiches
    Garantie-Niveau wie der manuelle Pattern."""
    track_id = 424_244
    inside = []
    overlap_seen = threading.Event()
    barrier = threading.Barrier(2)

    def worker() -> None:
        barrier.wait()  # beide gleichzeitig auf den Lock losgehen
        with audio_service.track_lock(track_id):
            inside.append(1)
            if len(inside) > 1:
                overlap_seen.set()
            # kurz halten damit der zweite Thread garantiert wartet
            import time
            time.sleep(0.05)
            inside.pop()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)
    assert not overlap_seen.is_set(), (
        "track_lock garantiert keine Serialisierung mehr — Lock-Semantik "
        "des Refcount-Patterns wurde im Refactor zerstoert."
    )
    after = _refs_snapshot()
    assert track_id not in after, (
        "Refcount-Cleanup nach concurrent Callers fehlerhaft — Eintrag "
        f"persistiert: {after}"
    )


def test_analyze_and_store_uses_track_lock_contextmanager() -> None:
    """Migration: ``AudioAnalyzer.analyze_and_store`` muss auf den
    ContextManager umgestellt sein — kein bares
    ``_get_track_lock``/``_release_track_lock`` mehr im Code.
    """
    src = inspect.getsource(audio_service.AudioAnalyzer.analyze_and_store)
    assert "track_lock(" in src, (
        "B-143 hardening: analyze_and_store nutzt den track_lock "
        "ContextManager nicht."
    )
    assert "_release_track_lock" not in src, (
        "B-143 hardening: bare _release_track_lock-Call in "
        "analyze_and_store — Migration unvollstaendig."
    )
