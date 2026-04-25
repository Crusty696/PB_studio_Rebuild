"""B-147 regression test: video pipeline cancel must mark status.

Each pipeline step calls ``mark_started`` first. On cancel
(``should_stop()`` returns True) it just ``return result`` — no
``mark_done``, no ``mark_error``. The row stays "running" forever.
After cancel the user can't re-analyze without DB surgery.

Fix: every cancel branch must mark the step as error (or a new
"cancelled" status) before returning.
"""

from __future__ import annotations

import inspect

from services import video_analysis_service


def test_cancel_branches_mark_status_before_return() -> None:
    """For each step in run_full_pipeline, the ``if should_stop()``
    cancel-branch must mark the step's status (mark_error /
    mark_cancelled) before returning."""
    src = inspect.getsource(video_analysis_service)

    # Heuristic: count cancel-branches vs cancel-mark calls within them.
    # We look for the pattern:
    #   if should_stop and should_stop():
    #       analysis_status_service.mark_error(...) | mark_cancelled(...)
    #       return ...
    cancel_branches = src.count("if should_stop and should_stop():")
    assert cancel_branches >= 4, (
        "Expected several cancel-branches in run_full_pipeline; the "
        "test inspection target may have changed."
    )

    # Each cancel-branch should now mention mark_error or mark_cancelled.
    # Crude line-by-line: find each ``if should_stop`` and check the next
    # 5 lines for one of the mark-functions.
    lines = src.splitlines()
    branches_without_mark = 0
    for i, line in enumerate(lines):
        if "if should_stop and should_stop():" not in line:
            continue
        window = "\n".join(lines[i:i + 8])
        if "mark_error" not in window and "mark_cancelled" not in window:
            branches_without_mark += 1

    assert branches_without_mark == 0, (
        f"BUG-147 regression: {branches_without_mark} cancel-branches "
        f"in run_full_pipeline still don't call mark_error/mark_cancelled. "
        f"User-cancel leaves analysis_status forever on 'running'."
    )
