"""B-136 regression test: ProjectManager active-wait for running tasks.

The TOCTOU check ``_has_running_tasks()`` returns immediately —
between the check and the actual ``set_project`` call, a new task
can start. Fix: bounded active-wait that polls until either tasks
go idle OR a timeout is reached.
"""

from __future__ import annotations

import inspect

from services.project_manager import ProjectManager


def test_active_wait_helper_present() -> None:
    """ProjectManager must define a dedicated active-wait helper that
    polls with a timeout. A bare ``if self._has_running_tasks()`` is
    insufficient (TOCTOU race)."""
    methods = [m for m in dir(ProjectManager) if not m.startswith("__")]
    has_wait_helper = any(
        m in methods
        for m in (
            "_wait_for_idle",
            "_wait_until_no_running_tasks",
            "_wait_for_tasks_idle",
        )
    )
    assert has_wait_helper, (
        "BUG-136 regression: ProjectManager must expose a dedicated "
        "wait helper (e.g. ``_wait_for_tasks_idle``) that polls "
        "_has_running_tasks() with a bounded timeout. The single-shot "
        "check is TOCTOU."
    )


def test_create_project_uses_active_wait() -> None:
    src = inspect.getsource(ProjectManager.create_project)
    assert (
        "_wait_for_idle" in src
        or "_wait_until_no_running" in src
        or "_wait_for_tasks_idle" in src
    ), (
        "BUG-136: create_project must call the active-wait helper "
        "instead of the single-shot _has_running_tasks check."
    )
