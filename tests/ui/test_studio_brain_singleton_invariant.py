"""B-115 / BUG-8-b regression-as-dismissal test:

Bug-hunter Trial 2026-04-25 (BUG-8-b, LOW, Confidence LOW): claimed
``StudioBrainWindow.instance()`` has a hypothetical race because the
``shiboken6.isValid`` check + ``cls._instance = cls()`` is not atomic.

Verification: all current callers (Ctrl+B shortcut, top-bar button)
are main-thread-only. The classmethod has no thread-safety contract
beyond "called from the Qt GUI thread".

This test asserts the structural invariant we DO rely on:
the shiboken6 validity check exists, so a stale Python reference
to a deleted C++ widget triggers re-creation rather than
``RuntimeError: Internal C++ object already deleted``.
"""

from __future__ import annotations

import inspect

from ui.studio_brain_window import StudioBrainWindow


def test_instance_uses_shiboken_validity_check() -> None:
    src = inspect.getsource(StudioBrainWindow.instance)
    assert "shiboken6.isValid" in src or "shiboken6" in src, (
        "BUG-8-b regression: StudioBrainWindow.instance() lost the "
        "shiboken6 validity check. Without it a stale Python reference "
        "to a deleted C++ QMainWindow raises "
        "``RuntimeError: Internal C++ object already deleted``."
    )
    # Both branches of the if must lead to a re-creation when invalid.
    assert "cls._instance = cls()" in src, (
        "BUG-8-b regression: instance() no longer re-creates the "
        "window when the singleton is stale. Re-creation is the whole "
        "point of the validity check."
    )
