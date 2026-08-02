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


def test_shutdown_waits_for_inflight_background_flush() -> None:
    """Project switch must not overtake PatternAggregator's second DB session."""
    worker = MemoryUpdaterWorker(
        session_factory=lambda: object(),
        batch_size=1,
        flush_delay_sec=0.0,
    )
    entered = threading.Event()
    release = threading.Event()

    def slow_run() -> int:
        entered.set()
        assert release.wait(timeout=2.0)
        return 1

    worker._aggregator.run = slow_run  # type: ignore[method-assign]
    assert worker.notify_feedback() is True
    assert entered.wait(timeout=1.0)

    result: list[int] = []
    shutdown_thread = threading.Thread(
        target=lambda: result.append(worker.shutdown(timeout_sec=2.0)),
    )
    shutdown_thread.start()
    time.sleep(0.05)
    assert shutdown_thread.is_alive(), "shutdown overtook active aggregation"

    release.set()
    shutdown_thread.join(timeout=1.0)
    assert not shutdown_thread.is_alive()
    assert result == [0]


def test_feedback_during_flush_rearms_debounce_after_inflight_finishes() -> None:
    """A timer firing during an active flush must not strand new feedback."""
    worker = MemoryUpdaterWorker(
        session_factory=lambda: object(),
        batch_size=1,
        flush_delay_sec=0.05,
    )
    first_entered = threading.Event()
    release_first = threading.Event()
    second_done = threading.Event()
    calls = 0

    def controlled_run() -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            first_entered.set()
            release_first.wait(timeout=2.0)
        else:
            second_done.set()
        return 1

    worker._aggregator.run = controlled_run  # type: ignore[method-assign]
    assert worker.notify_feedback() is True
    assert first_entered.wait(timeout=1.0)
    assert worker.notify_feedback() is False

    time.sleep(0.1)  # first debounce fires while flush #1 is still active
    release_first.set()

    assert second_done.wait(timeout=1.0), "new feedback remained pending forever"
    assert calls == 2


def test_shutdown_waits_for_successor_flush_generation() -> None:
    """An older completion must not release waiters for a successor flush."""
    worker = MemoryUpdaterWorker(
        session_factory=lambda: object(),
        batch_size=1,
        flush_delay_sec=0.01,
    )
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()
    release_second = threading.Event()
    calls = 0

    def controlled_run() -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            first_entered.set()
            assert release_first.wait(timeout=2.0)
        else:
            second_entered.set()
            assert release_second.wait(timeout=2.0)
        return 1

    worker._aggregator.run = controlled_run  # type: ignore[method-assign]
    assert worker.notify_feedback() is True
    assert first_entered.wait(timeout=1.0)
    assert worker.notify_feedback() is False
    release_first.set()
    assert second_entered.wait(timeout=1.0)

    result: list[int] = []
    shutdown_thread = threading.Thread(
        target=lambda: result.append(worker.shutdown(timeout_sec=2.0)),
    )
    shutdown_thread.start()
    time.sleep(0.05)
    assert shutdown_thread.is_alive(), "shutdown accepted stale flush completion"

    release_second.set()
    shutdown_thread.join(timeout=1.0)
    assert not shutdown_thread.is_alive()
    assert result == [0]


def test_strict_shutdown_propagates_error_and_restores_pending() -> None:
    """Lifecycle flush failure must be visible and retryable."""
    worker = MemoryUpdaterWorker(
        session_factory=lambda: object(),
        batch_size=20,
        flush_delay_sec=0.0,
    )
    assert worker.notify_feedback() is False

    def fail() -> int:
        raise RuntimeError("aggregation failed")

    worker._aggregator.run = fail  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="aggregation failed"):
        worker.shutdown(raise_on_error=True)
    assert worker.pending_events == 1

    worker._aggregator.run = lambda: 2  # type: ignore[method-assign]
    assert worker.shutdown(raise_on_error=True) == 2
    assert worker.pending_events == 0


def test_shutdown_drains_feedback_arriving_during_its_own_flush() -> None:
    """Project switch may return only after its own successor generation."""
    worker = MemoryUpdaterWorker(
        session_factory=lambda: object(),
        batch_size=20,
        flush_delay_sec=30.0,
    )
    first_entered = threading.Event()
    release_first = threading.Event()
    second_done = threading.Event()
    calls = 0

    def controlled_run() -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            first_entered.set()
            assert release_first.wait(timeout=2.0)
        else:
            second_done.set()
        return 1

    worker._aggregator.run = controlled_run  # type: ignore[method-assign]
    assert worker.notify_feedback() is False

    result: list[int] = []
    shutdown_thread = threading.Thread(
        target=lambda: result.append(worker.shutdown(timeout_sec=2.0)),
    )
    shutdown_thread.start()
    assert first_entered.wait(timeout=1.0)
    assert worker.notify_feedback() is False
    release_first.set()

    assert second_done.wait(timeout=1.0)
    shutdown_thread.join(timeout=1.0)
    assert not shutdown_thread.is_alive()
    assert result == [2]
    assert worker.pending_events == 0


def test_best_effort_shutdown_stops_after_persistent_error() -> None:
    """atexit best-effort must preserve pending without retry loop/log storm."""
    worker = MemoryUpdaterWorker(
        session_factory=lambda: object(),
        batch_size=20,
        flush_delay_sec=0.0,
    )
    calls = 0

    def fail() -> int:
        nonlocal calls
        calls += 1
        raise RuntimeError("persistent DB failure")

    worker._aggregator.run = fail  # type: ignore[method-assign]
    assert worker.notify_feedback() is False

    started = time.monotonic()
    assert worker.shutdown(timeout_sec=0.1, raise_on_error=False) == 0

    assert time.monotonic() - started < 0.5
    assert calls == 1
    assert worker.pending_events == 1
