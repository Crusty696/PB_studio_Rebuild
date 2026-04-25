"""B-111 / BUG-11-b regression test:

``MediaWorkspace._on_grid_run_all`` had two issues:
1. ``dispatched = True`` was unreachable for video media (``break``
   exited the loop before the assignment). Dead code.
2. Audio dispatch errors were caught and logged but the loop
   continued, so a second step would register a task even if the
   first errored.

We assert the dead-code variable is gone and the loop breaks on
audio errors as well.
"""

from __future__ import annotations

import inspect

from ui.workspaces.media_workspace import MediaWorkspace


def test_on_grid_run_all_no_dead_dispatched_variable() -> None:
    src = inspect.getsource(MediaWorkspace._on_grid_run_all)
    # Either the variable is gone, or it is actually used (referenced
    # in a return / log / decision).
    has_decl = "dispatched = False" in src or "dispatched = True" in src
    has_use = src.count("dispatched") > src.count("dispatched = ")
    assert (not has_decl) or has_use, (
        "BUG-11-b regression: ``dispatched`` is declared but never "
        "consumed (dead code)."
    )


def test_on_grid_run_all_breaks_on_audio_dispatch_error() -> None:
    """Audio dispatch errors must break the loop, not silently
    continue to the next step (which could register a second task)."""
    src = inspect.getsource(MediaWorkspace._on_grid_run_all)
    # Heuristic: look for ``break`` inside an exception handler. The
    # exact shape depends on the fix style; either ``break`` or
    # ``return`` after the log call is acceptable.
    assert "break" in src or "return" in src, (
        "BUG-11-b: _on_grid_run_all must break/return the loop on "
        "dispatch errors so a failed first step does not register a "
        "second task."
    )
    # Stronger: the except block must mention a flow-control keyword.
    except_idx = src.find("except Exception")
    assert except_idx != -1, "Expected except block in _on_grid_run_all"
    after_except = src[except_idx:]
    assert "break" in after_except or "return" in after_except, (
        "BUG-11-b: the except block in _on_grid_run_all silently "
        "continues. Add break/return so partial-failure does not "
        "compound."
    )
