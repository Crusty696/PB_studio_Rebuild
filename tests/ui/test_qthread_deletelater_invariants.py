"""B-107 / BUG-A5 + BUG-A6 + BUG-A11 regression tests:

QThread cleanup-via-deleteLater patterns. The convention across this
codebase is:

    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)

Missing either line leaks the QObject's C++ shell. Calling deleteLater
twice is harmless (Qt schedules a single pending-delete) but indicates
the wiring is duplicated and brittle — refactor risk.

We assert the invariants by source-inspecting the producer functions.
Runtime leak detection would be flaky in CI.
"""

from __future__ import annotations

import inspect


def test_media_grid_thumb_loader_uses_bounded_pool() -> None:
    """B-508 (ersetzt BUG-A5): ``MediaPoolGrid._start_thumb_loader``
    darf KEINE per-Card-QThreads mehr starten — Thumbnails laufen ueber
    den geteilten, begrenzten ``QThreadPool`` (max. 4). Das frueher hier
    geforderte deleteLater-Wiring entfaellt: ``setAutoDelete(True)``
    laesst den Pool das Runnable nach run() selbst abraeumen."""
    from ui.widgets.media_grid import (
        MediaPoolGrid, _ThumbRunnable, _get_thumb_pool,
        _THUMB_POOL_MAX_THREADS,
    )

    src = inspect.getsource(MediaPoolGrid._start_thumb_loader)
    assert "QThread(" not in src, (
        "B-508 regression: _start_thumb_loader spawnt wieder per-Card-"
        "QThreads statt den geteilten Pool zu nutzen."
    )
    assert "_get_thumb_pool().start" in src, (
        "B-508: _start_thumb_loader muss Jobs ueber _get_thumb_pool() starten."
    )

    rsrc = inspect.getsource(_ThumbRunnable.__init__)
    assert "setAutoDelete(True)" in rsrc, (
        "B-508: _ThumbRunnable braucht setAutoDelete(True), sonst leakt "
        "ein Runnable-Shell pro Thumbnail."
    )

    assert _THUMB_POOL_MAX_THREADS == 4
    assert _get_thumb_pool().maxThreadCount() == 4, (
        "B-508: geteilter Thumbnail-Pool muss auf 4 Threads begrenzt sein."
    )


def test_timeline_db_worker_deletes_worker_and_thread() -> None:
    """BUG-A11: timeline DB-load wiring must include both
    thread.deleteLater AND worker.deleteLater so the worker shell does
    not leak per project-switch / timeline-reload."""
    from ui.timeline import InteractiveTimeline

    # The wiring sits inside _load_data_async. Inspect the method.
    method = getattr(InteractiveTimeline, "_load_data_async", None)
    if method is None:
        # In some refactors the loader is named differently — fall back to
        # the entire class source.
        src = inspect.getsource(InteractiveTimeline)
    else:
        src = inspect.getsource(method)
    assert "_db_thread.deleteLater" in src or "thread.deleteLater" in src, (
        "BUG-A11: timeline must wire db_thread.deleteLater."
    )
    assert "_db_worker.deleteLater" in src or "worker.deleteLater" in src, (
        "BUG-A11: timeline must wire db_worker.deleteLater. Without "
        "it, every timeline reload leaks one TimelineDBWorker shell."
    )


def test_chat_dock_does_not_double_schedule_deletelater() -> None:
    """BUG-A6: ``ChatDock`` had deleteLater scheduled twice — once via
    ``thread.finished.connect(...)`` and once inside ``_cleanup_thread``.
    Idempotent in Qt but indicates duplicated wiring. Fix: pick one path
    (the signal/slot one is preferred — declarative + survives even if
    _cleanup_thread is replaced by something else).
    """
    from ui import chat_dock as mod

    src = inspect.getsource(mod)

    # Either:
    # - Signal-connection path stays, _cleanup_thread no longer calls deleteLater.
    # - OR _cleanup_thread stays, signal-connection path drops deleteLater calls.
    #
    # We assert that we are NOT in the "both path" state. Count occurrences
    # of explicit deleteLater calls on _worker / _thread inside the chat
    # dock module: must NOT have BOTH the signal-connect path
    # ("thread.finished.connect(worker.deleteLater)") AND a manual
    # "_worker.deleteLater()" call inside _cleanup_thread.
    has_signal_connect_worker = (
        "thread.finished.connect(worker.deleteLater)" in src
    )
    has_cleanup_manual_worker = (
        "self._worker.deleteLater()" in src
    )
    assert not (has_signal_connect_worker and has_cleanup_manual_worker), (
        "BUG-A6 regression: ChatDock has BOTH signal-connect "
        "deleteLater AND manual deleteLater in _cleanup_thread. Pick "
        "one path so deleteLater is scheduled exactly once. Currently: "
        f"signal={has_signal_connect_worker}, manual={has_cleanup_manual_worker}"
    )
