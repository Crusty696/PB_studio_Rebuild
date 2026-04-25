"""B-143 regression test: _track_locks must use refcount, not pop-after-release.

Cycle-4 tester: H-10's "memory leak" fix popped ``_track_locks[track_id]``
inside the same with-block as ``_analyze_and_store_locked``. Sequence:

  T1 acquires L1
  T2 sees L1, blocks on it
  T1 finishes work, pops _track_locks[5], releases L1
  T3 calls _get_track_lock(5) → dict empty → creates L2, acquires L2
  T2 wakes (L1)
  T2 + T3 now hold DIFFERENT locks → run analyze() concurrently → DB race

The lock that was supposed to PREVENT concurrent analyze for the same
track_id allowed it.

Fix: refcount on each key. Increment on _get_track_lock, decrement +
remove only when refcount==0 — all under _track_locks_guard.
"""

from __future__ import annotations

import inspect

from services import audio_service


def test_get_track_lock_uses_refcount_not_pop_after_release() -> None:
    """``_get_track_lock`` must increment a refcount, and the cleanup
    site must only remove when refcount==0."""
    src = inspect.getsource(audio_service)
    has_refcount_pattern = (
        "_track_lock_refs" in src
        or "_lock_refcount" in src
        or "refcount" in src.lower()
    )
    assert has_refcount_pattern, (
        "BUG-143 regression: audio_service still uses pop-after-release "
        "on _track_locks. T2 waiting on a lock can be skipped by T3 "
        "creating a new lock for the same key. Use refcount."
    )


def test_analyze_and_store_does_not_pop_lock_after_release() -> None:
    """The cleanup branch in ``analyze_and_store`` must NOT call
    ``_track_locks.pop()`` immediately after work — that's the H-10 race.
    Either remove the pop entirely (defer to refcount) or leave the
    entry permanently (memory cost is negligible)."""
    src = inspect.getsource(audio_service.AudioAnalyzer.analyze_and_store)
    # The body must NOT contain a bare ``_track_locks.pop`` inside the
    # finally — that's the H-10 anti-pattern.
    assert "_track_locks.pop" not in src, (
        "BUG-143: analyze_and_store still pops the lock in finally. "
        "Use refcount-based cleanup or simply leave the entry."
    )
