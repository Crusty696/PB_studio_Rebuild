"""B-598: Timeline/AutoEdit Finish-Guardrails gegen Mainthread-Freeze."""
from __future__ import annotations

import inspect


def test_b598_timeline_overlay_updates_have_signatures_and_timing_logs() -> None:
    from ui.timeline import InteractiveTimeline

    beat_source = inspect.getsource(InteractiveTimeline.set_beat_markers)
    cut_source = inspect.getsource(InteractiveTimeline.set_cut_points)

    assert "_beat_marker_signature" in beat_source
    assert "B-598 timeline set_beat_markers" in beat_source
    assert "_cut_points_signature" in cut_source
    assert "B-598 timeline set_cut_points" in cut_source


def test_b598_load_from_db_logs_teardown_duration() -> None:
    from ui.timeline import InteractiveTimeline

    source = inspect.getsource(InteractiveTimeline.load_from_db)
    assert "B-598 timeline load_from_db teardown" in source
    assert "time.perf_counter" in source


def test_b598_auto_edit_redo_logs_apply_and_reload_duration() -> None:
    from ui.undo_commands import ApplyAutoEditCommand

    source = inspect.getsource(ApplyAutoEditCommand.redo)
    assert "B-598 ApplyAutoEditCommand.redo apply_auto_edit_segments" in source
    assert "B-598 ApplyAutoEditCommand.redo load_from_db" in source


def test_b598_edit_workspace_defers_finish_refreshes() -> None:
    from ui.controllers.edit_workspace import EditWorkspaceController

    source = inspect.getsource(EditWorkspaceController)
    assert "_defer_cut_list_refresh" in source
    assert "_defer_schnitt_workspace_refresh" in source
    assert "QTimer.singleShot(0, _refresh)" in source
