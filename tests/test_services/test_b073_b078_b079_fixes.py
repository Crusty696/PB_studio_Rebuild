"""Verify-Tests fuer B-073, B-078, B-079.

- B-073: Retry-Loops in FrequencyAnalyzer + BeatAnalysisService nutzen
  exponential backoff + random jitter (statt linearer 2/4/6s).
- B-078: TimelineService.timeline-Lazy-Init ist thread-safe via Lock.
- B-079: ``_do_apply_segments`` nutzt ``nullpool_session()`` statt eines
  eigenen Engine-Setups (DRY + foreign_keys=ON + busy_timeout=120s).
"""

from __future__ import annotations

import inspect
import threading
import time

import pytest


# --------------------------------------------------------------------------
# B-073: Retry mit Jitter
# --------------------------------------------------------------------------

def test_b073_frequency_analyzer_retry_uses_jitter() -> None:
    """Source-Inspektion: FrequencyAnalyzer-Retry hat random.uniform-Jitter."""
    from services import ai_audio_service

    src = inspect.getsource(ai_audio_service.FrequencyAnalyzer)
    assert "B-073" in src, "B-073-Marker fehlt im FrequencyAnalyzer-Source"
    assert "random.uniform" in src or "_random.uniform" in src, (
        "B-073: kein random.uniform-Jitter in FrequencyAnalyzer-Retry"
    )
    assert "2 ** attempt" in src, (
        "B-073: kein exponential backoff (2 ** attempt) in FrequencyAnalyzer-Retry"
    )


def test_b073_beat_analysis_retry_uses_jitter() -> None:
    """Source-Inspektion: BeatAnalysisService-Retry hat random.uniform-Jitter."""
    from services import beat_analysis_service

    src = inspect.getsource(beat_analysis_service.BeatAnalysisService)
    assert "B-073" in src, "B-073-Marker fehlt im BeatAnalysisService-Source"
    assert "random.uniform" in src or "_random.uniform" in src, (
        "B-073: kein random.uniform-Jitter in BeatAnalysisService-Retry"
    )
    assert "2 ** attempt" in src, (
        "B-073: kein exponential backoff (2 ** attempt) in BeatAnalysisService-Retry"
    )


# --------------------------------------------------------------------------
# B-078: TimelineService Lazy-Init Race
# --------------------------------------------------------------------------

def test_b078_timeline_service_has_lock() -> None:
    """TimelineService besitzt ``_timeline_lock`` als threading.Lock."""
    from services.timeline_service import TimelineService

    svc = TimelineService(fps=30.0)
    assert hasattr(svc, "_timeline_lock"), "B-078: _timeline_lock fehlt"
    # threading.Lock returns a _thread.lock — duck-type check via acquire/release
    assert callable(getattr(svc._timeline_lock, "acquire", None))
    assert callable(getattr(svc._timeline_lock, "release", None))


def test_b078_concurrent_lazy_init_returns_single_timeline() -> None:
    """Zwei Threads triggern den Lazy-Getter gleichzeitig — beide bekommen
    DIESELBE Timeline-Instanz, nicht zwei verschiedene."""
    from services.timeline_service import TimelineService

    svc = TimelineService(fps=30.0)
    barrier = threading.Barrier(2)
    results: list = []

    def _worker() -> None:
        barrier.wait()  # synchronisiert beide Threads exakt am Getter-Aufruf
        results.append(svc.timeline)

    t1 = threading.Thread(target=_worker)
    t2 = threading.Thread(target=_worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert len(results) == 2
    assert results[0] is results[1], (
        "B-078: zwei Threads haben verschiedene Timeline-Instanzen erhalten — "
        "Lazy-Init Race nicht abgesichert."
    )


# --------------------------------------------------------------------------
# B-079: _do_apply_segments nutzt nullpool_session
# --------------------------------------------------------------------------

def test_b079_do_apply_segments_uses_nullpool_session() -> None:
    """Source-Inspektion: ``_do_apply_segments`` ruft ``nullpool_session()``
    statt eigenes ``create_engine`` zu bauen."""
    from services import timeline_service

    src = inspect.getsource(timeline_service._do_apply_segments)
    assert "nullpool_session" in src, (
        "B-079: _do_apply_segments nutzt nicht den kanonischen Helper"
    )
    # Negativ-Snapshot: keine eigene create_engine + NullPool-Konstruktion mehr
    assert "create_engine" not in src, (
        "B-079: _do_apply_segments hat noch eine eigene create_engine-Konstruktion"
    )
    assert "poolclass=NullPool" not in src, (
        "B-079: _do_apply_segments hat noch eigenes poolclass=NullPool"
    )


def test_b079_do_apply_segments_no_explicit_dispose() -> None:
    """``nullpool_session`` macht den Dispose im __exit__ — der Caller
    soll ihn nicht doppelt aufrufen.
    """
    from services import timeline_service

    src = inspect.getsource(timeline_service._do_apply_segments)
    assert "_eng.dispose" not in src, (
        "B-079: _do_apply_segments macht doppelten dispose"
    )
