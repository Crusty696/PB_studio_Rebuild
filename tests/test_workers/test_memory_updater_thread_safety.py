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


def test_notify_feedback_warns_when_run_triggers_on_gui_thread(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When ``notify_feedback()`` triggers a flush AND the calling thread
    is the Qt GUI thread, the worker must emit a warning so the wiring
    bug surfaces in dev/test. We use batch_size=1 so the very first
    feedback flushes."""
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])

    def fake_session() -> object:
        class _S:
            def execute(self, *a, **kw):  # noqa: ANN001
                class _R:
                    def mappings(self):
                        return self
                    def all(self):
                        return []
                return _R()
            def close(self):
                pass
        return _S()

    worker = MemoryUpdaterWorker(session_factory=fake_session, batch_size=1)

    with caplog.at_level(logging.WARNING, logger="workers.memory_updater"):
        worker.notify_feedback()  # flush triggers on main thread

    assert "GUI thread" in caplog.text, (
        f"BUG-2-b: expected GUI-thread warning when notify_feedback() "
        f"flushes on the main thread. caplog: {caplog.text}"
    )
