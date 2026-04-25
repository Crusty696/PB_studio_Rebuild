"""Cycle-2 LOW batch regression tests.

Covers:
- B-126 per-segment _run_ffmpeg cancel_check propagation
- B-127 TaskManagerDock per-row cancel
- B-128 TaskDock total=0 progress edge case
- B-130 LocalAgentService.record_feedback utcnow → now(timezone.utc)
"""

from __future__ import annotations

import inspect

from services import export_service, local_agent_service


def test_b126_export_optimized_concat_propagates_cancel_to_per_segment_ffmpeg() -> None:
    """B-126: ``_export_optimized_concat`` must pass cancel_check through
    to its per-segment ``_run_ffmpeg(std_cmd, ...)`` calls."""
    src = inspect.getsource(export_service._export_optimized_concat)
    # Find _run_ffmpeg(std_cmd ...) calls; assert cancel_check appears
    # somewhere within ~200 chars (in the kwargs).
    needle = "_run_ffmpeg(std_cmd"
    pos = src.find(needle)
    while pos != -1:
        window = src[pos:pos + 400]
        assert "cancel_check" in window, (
            f"BUG-126: per-segment _run_ffmpeg call at offset {pos} of "
            f"_export_optimized_concat has no cancel_check propagation. "
            f"Window: {window!r}"
        )
        pos = src.find(needle, pos + 1)


def test_b126_preprocess_segment_propagates_cancel_check() -> None:
    """B-126: ``_preprocess_segment`` (helper used by both export paths)
    must accept and propagate cancel_check."""
    sig = inspect.signature(export_service._preprocess_segment)
    assert "cancel_check" in sig.parameters, (
        "BUG-126: _preprocess_segment must accept cancel_check kwarg."
    )


def test_b127_task_dock_has_per_row_cancel() -> None:
    """B-127: TaskManagerDock should provide per-row cancel buttons or
    at least an "Alle abbrechen" mechanism. We accept either pattern."""
    from ui.widgets import task_manager_dock as dock_mod
    src = inspect.getsource(dock_mod)
    # Per-row: a cancel button is added when a row is created.
    has_per_row = (
        "row_cancel" in src
        or "per_row_cancel" in src
        or "cancel_btn" in src
    )
    # OR: cancel-all path that doesn't only pick the longest.
    has_cancel_all = "_on_cancel_all_clicked" in src or "cancel_all" in src
    assert has_per_row or has_cancel_all, (
        "BUG-127: TaskManagerDock still cancels only the longest task. "
        "Add per-row cancel buttons or a 'cancel all' mechanism."
    )


def test_b128_dock_handles_zero_total() -> None:
    """B-128: ``_on_task_updated`` must handle the case where
    ``task.total == 0`` (e.g. indeterminate progress). We expect either
    a setRange(0, 0) indeterminate fallback OR explicit handling."""
    from ui.widgets import task_manager_dock as dock_mod
    src = inspect.getsource(dock_mod.TaskManagerDock._on_task_updated)
    # The fix should remove the bare `if task.total > 0:` guard or
    # add an explicit elif for the zero-total case.
    has_fallback = (
        "setRange(0, 0)" in src  # indeterminate
        or "elif task.progress" in src
        or "task.total == 0" in src
        or "indeterminate" in src.lower()
    )
    assert has_fallback, (
        "BUG-128: _on_task_updated still ignores task.total == 0 case. "
        "Workers reporting progress without total see fake-0%."
    )


def test_b130_record_feedback_uses_timezone_utc() -> None:
    """B-130: ``LocalAgentService.record_feedback`` must use
    ``datetime.now(timezone.utc)`` (not deprecated utcnow)."""
    src = inspect.getsource(local_agent_service.LocalAgentService.record_feedback)
    assert "datetime.utcnow" not in src, (
        "BUG-130: record_feedback still uses deprecated datetime.utcnow. "
        "Use datetime.now(timezone.utc)."
    )
    # Positive: must mention timezone or utc-aware now.
    assert ("timezone.utc" in src or "now(timezone" in src), (
        "BUG-130: record_feedback must use datetime.now(timezone.utc)."
    )
