"""B3 — InteractiveTimeline.undo_stack ist pro Instanz eigen.

Tier-1 Hardening 2026-05-09 (SCHNITT Redesign).
"""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


def test_two_timelines_have_independent_undo_stacks():
    _qapp()
    from ui.timeline import InteractiveTimeline

    a = InteractiveTimeline()
    b = InteractiveTimeline()

    assert isinstance(a.undo_stack, QUndoStack)
    assert isinstance(b.undo_stack, QUndoStack)
    assert a.undo_stack is not b.undo_stack


def test_undo_stack_owned_by_view():
    _qapp()
    from ui.timeline import InteractiveTimeline

    t = InteractiveTimeline()
    # QUndoStack-Parent ist der View — kein "stale parent"-Risk
    assert t.undo_stack.parent() is t
