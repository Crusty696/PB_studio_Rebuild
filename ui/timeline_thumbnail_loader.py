"""B-471 T1 — viewport-lazy thumbnail load scheduler for the timeline.

Pure scheduling logic (no Qt), so it is unit-testable without a QApplication.
The actual async thumbnail worker is injected via ``start_worker(file_path)``.

Usage from the timeline view:
- for each VISIBLE video clip lacking a thumbnail, call ``request(file_path)``;
- the manager dedups, caps concurrency, and calls ``start_worker(file_path)``
  for the ones that should run now;
- when a worker finishes, call ``on_done(file_path)`` so the next queued one
  starts.

This prevents the naive "1132 clips -> 1132 ffmpeg jobs" blow-up: only visible
clips are requested, each file is generated at most once, and at most
``max_concurrent`` run at a time.
"""

from __future__ import annotations

from collections import deque
from typing import Callable


class ThumbnailLoadManager:
    def __init__(self, start_worker: Callable[[str], None], max_concurrent: int = 2):
        self._start_worker = start_worker
        self._max_concurrent = max(1, int(max_concurrent))
        self._queue: deque[str] = deque()
        self._queued: set[str] = set()
        self._inflight: set[str] = set()
        self._done: set[str] = set()

    def request(self, file_path: str | None) -> None:
        """Enqueue a thumbnail generation for *file_path* (deduped)."""
        if not file_path:
            return
        if (file_path in self._done
                or file_path in self._inflight
                or file_path in self._queued):
            return
        self._queue.append(file_path)
        self._queued.add(file_path)
        self._pump()

    def on_done(self, file_path: str) -> None:
        """Mark a worker finished; start the next queued one."""
        self._inflight.discard(file_path)
        self._done.add(file_path)
        self._pump()

    def is_done(self, file_path: str) -> bool:
        return file_path in self._done

    def reset(self) -> None:
        """Forget queue + inflight (e.g. on project switch). Keeps `_done`
        so already-generated thumbs are not regenerated."""
        self._queue.clear()
        self._queued.clear()
        self._inflight.clear()

    @property
    def inflight_count(self) -> int:
        return len(self._inflight)

    @property
    def queued_count(self) -> int:
        return len(self._queue)

    def _pump(self) -> None:
        while self._queue and len(self._inflight) < self._max_concurrent:
            fp = self._queue.popleft()
            self._queued.discard(fp)
            self._inflight.add(fp)
            self._start_worker(fp)
