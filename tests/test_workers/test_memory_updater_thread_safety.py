"""B-105 / BUG-2-b regression tests:

``MemoryUpdaterWorker.notify_feedback()`` previously incremented
``self._pending`` without a lock and called ``self.run()`` synchronously
on the caller's thread. Two issues:

1. TOCTOU race: ``self._pending += 1`` is not atomic. Concurrent
   notify_feedback() calls from multiple threads can lose increments
   and either fail to flush or flush multiple times.
2. Sync run on UI thread: when the batch threshold triggers,
   ``self.run()`` does the SQL aggregation on whatever thread called
   ``notify_feedback()`` — if that's the Qt GUI thread, the multi-second
   aggregation freezes the UI.

These tests exercise both paths.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from workers.memory_updater import MemoryUpdaterWorker


def test_notify_feedback_uses_lock_for_pending_counter() -> None:
    """Structural assertion: ``MemoryUpdaterWorker`` must own a
    ``threading.Lock`` to coordinate ``_pending`` mutation across
    threads. Pure race-condition tests are flaky against the GIL
    (race windows close before pytest can observe them deterministically),
    so we assert the FIX is structurally present instead.

    Without the lock the bug is real and well-understood: at the
    threshold boundary two concurrent ``notify_feedback()`` calls can
    both observe ``_pending >= batch_size`` and concurrently invoke
    ``run()`` — but the GIL makes this hard to demonstrate
    deterministically in a small test."""
    def fake_session() -> object:
        class _S: pass
        return _S()
    worker = MemoryUpdaterWorker(session_factory=fake_session, batch_size=20)

    # The fix must add a lock attribute. We don't care about the exact
    # name, just that one lock-like object lives on the worker.
    lock_attrs = [
        a for a in dir(worker)
        if not a.startswith("__") and "lock" in a.lower()
    ]
    assert lock_attrs, (
        "BUG-2-b regression: MemoryUpdaterWorker has no Lock-like "
        "attribute. ``_pending += 1`` followed by ``run()`` is a "
        "TOCTOU race; needs a threading.Lock."
    )
    # Confirm at least one is actually a lock (acquire/release present).
    assert any(
        hasattr(getattr(worker, a), "acquire")
        and hasattr(getattr(worker, a), "release")
        for a in lock_attrs
    ), (
        f"BUG-2-b regression: lock-named attribute is not a real lock: "
        f"{lock_attrs}"
    )


def test_notify_feedback_batch_trigger_does_not_block_caller_thread() -> None:
    """Batch-trigger darf nicht synchron im Timeline/UI-Caller laufen."""
    def fake_session() -> object:
        class _S: pass
        return _S()

    worker = MemoryUpdaterWorker(session_factory=fake_session, batch_size=1)
    started = threading.Event()
    release = threading.Event()
    calls = []

    def slow_run() -> int:
        calls.append(threading.current_thread().name)
        started.set()
        release.wait(timeout=2.0)
        return 0

    worker._aggregator.run = slow_run  # type: ignore[method-assign]

    t0 = time.perf_counter()
    assert worker.notify_feedback() is True
    elapsed = time.perf_counter() - t0

    assert elapsed < 0.1
    assert started.wait(timeout=1.0)
    assert calls and calls[0] != threading.current_thread().name
    release.set()


def test_concurrent_batch_trigger_starts_exactly_one_flush() -> None:
    """Zwei parallele Feedback-Events am Schwellwert duerfen nicht doppelt flushen."""
    def fake_session() -> object:
        class _S: pass
        return _S()

    worker = MemoryUpdaterWorker(session_factory=fake_session, batch_size=2)
    worker._pending = 1
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def slow_run() -> int:
        calls.append(threading.current_thread().name)
        entered.set()
        release.wait(timeout=2.0)
        return 0

    worker._aggregator.run = slow_run  # type: ignore[method-assign]

    barrier = threading.Barrier(3)
    results = []

    def notify() -> None:
        barrier.wait(timeout=1.0)
        results.append(worker.notify_feedback())

    threads = [threading.Thread(target=notify) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=1.0)
    assert entered.wait(timeout=1.0)
    for thread in threads:
        thread.join(timeout=1.0)
    release.set()

    assert calls == [calls[0]]
    assert results.count(True) == 1
