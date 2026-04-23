"""SteerOverrideQueue — process-wide in-memory queue of pending clip-level
overrides (T10.2e).

The Structure tab (producer) pushes user intent here via ``add()``; the
future Steer tab (T11.3, consumer) will read via ``list()`` and drain via
``clear()``. Emits ``pendingChanged`` on every mutation so the Steer tab
can refresh its list in real time.

Design constraints:

- **Pure Python** — no DB access. Nothing in this module touches the
  SQLAlchemy session. Persistence is a Steer-tab concern
  (``mem_pacing_run.steer_snapshot``), landing in T11.3.
- **Process-wide singleton** via the module-level ``get_default_queue()``
  factory. ``StudioBrainWindow`` owns exactly one and passes it to child
  tabs; tests may inject their own via the ``override_queue`` kwarg.
- **Mutually-exclusive actions per scene_id**: ``boost`` and ``exclude``
  replace each other for the same ``scene_id``. We never stack both on
  one scene — the last-writer-wins semantics keep the queue a clean
  projection of current intent.
- ``pendingChanged`` carries no payload. The consumer queries
  ``.list()`` when it receives the signal.
- ``PendingOverride`` is frozen so callers can hand references across
  threads / widgets without worrying about surprise mutation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from PySide6.QtCore import QObject, Signal


Action = Literal["boost", "exclude"]


@dataclass(frozen=True)
class PendingOverride:
    """One user-queued override against a specific clip.

    Attributes
    ----------
    scene_id
        Target scene. Unique within the queue — a second ``add()`` for
        the same scene_id replaces the prior entry.
    action
        Either ``"boost"`` or ``"exclude"``. The two are mutually exclusive
        per scene_id.
    source
        Free-form audit string describing where the intent came from
        (``"inspector"`` for toolbar buttons, ``"structure"`` for grid
        card context-menu, ``"graph"`` for graph-view context-menu). We
        keep it a ``str`` — if T11.3 needs stricter typing we can enum-ify
        then.
    """

    scene_id: int
    action: Action
    source: str


class SteerOverrideQueue(QObject):
    """Process-wide in-memory queue of pending clip-level overrides.

    See module docstring for the design contract. Internally backed by
    an ordered dict keyed on ``scene_id`` so insertion order is preserved
    while still giving O(1) lookups / replacements.
    """

    pendingChanged = Signal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        # Dict preserves insertion order on Python 3.7+.
        self._items: dict[int, PendingOverride] = {}

    # ── mutations ─────────────────────────────────────────────────────────
    def add(self, scene_id: int, action: Action, source: str) -> None:
        """Queue an override. Replaces any existing entry for the same
        ``scene_id`` (boost/exclude are mutually exclusive).

        ``pendingChanged`` is emitted only on an **actual** mutation: a
        redundant ``add()`` producing a PendingOverride structurally equal
        to the existing entry for this ``scene_id`` is a no-op (mirrors the
        contract already honoured by ``remove()`` and ``clear()``).
        """
        if action not in ("boost", "exclude"):
            raise ValueError(
                f"action must be 'boost' or 'exclude', got {action!r}"
            )
        sid = int(scene_id)
        new = PendingOverride(scene_id=sid, action=action, source=str(source))
        if self._items.get(sid) == new:
            return
        self._items[sid] = new
        self.pendingChanged.emit()

    def remove(self, scene_id: int) -> None:
        """Drop the entry for ``scene_id`` if present. No-op otherwise
        (still emits ``pendingChanged`` only if we actually changed state)."""
        sid = int(scene_id)
        if sid in self._items:
            del self._items[sid]
            self.pendingChanged.emit()

    def clear(self) -> None:
        """Drop every queued override. Emits ``pendingChanged`` only when
        we actually had entries to drop."""
        if self._items:
            self._items.clear()
            self.pendingChanged.emit()

    # ── reads ─────────────────────────────────────────────────────────────
    def list(self) -> list[PendingOverride]:
        """Return a defensive copy of the current queue, in insertion order."""
        return list(self._items.values())

    def count(self) -> int:
        return len(self._items)


# ── Process-wide singleton factory ────────────────────────────────────────────

_default_queue: Optional[SteerOverrideQueue] = None


def get_default_queue() -> SteerOverrideQueue:
    """Return the shared process-wide SteerOverrideQueue, creating it lazily.

    The Structure tab's default constructor uses this when no queue is
    injected. ``StudioBrainWindow`` pulls the same singleton so all tabs
    (current + future Steer tab) observe the same queue.
    """
    global _default_queue
    if _default_queue is None:
        _default_queue = SteerOverrideQueue()
    return _default_queue


def reset_default_queue_for_test() -> None:
    """Test-only: wipe the process-wide singleton so a subsequent
    ``get_default_queue()`` rebuilds from scratch."""
    global _default_queue
    _default_queue = None


__all__ = [
    "Action",
    "PendingOverride",
    "SteerOverrideQueue",
    "get_default_queue",
    "reset_default_queue_for_test",
]
