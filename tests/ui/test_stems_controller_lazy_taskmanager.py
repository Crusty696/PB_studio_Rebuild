"""B-110 / BUG-13-b regression test:

``ui/controllers/stems.py`` had a module-level
``task_manager = TaskManagerProxy()`` — same pattern that L-38 fixed
in ``ui/controllers/video_analysis.py``. Module-level instantiation
breaks any caller that imports the module before QApplication exists
(unit tests, CLI tools, alembic env, …).

This test asserts the same lazy-init helper exists.
"""

from __future__ import annotations

import inspect

from ui.controllers import stems as stems_mod


def test_stems_controller_uses_lazy_task_manager() -> None:
    src = inspect.getsource(stems_mod)

    # Match the standalone line (not _task_manager which is the lazy slot).
    import re
    assert not re.search(
        r"^task_manager\s*=\s*TaskManagerProxy\(\)", src, re.MULTILINE
    ), (
        "BUG-13-b regression: module-level "
        "``task_manager = TaskManagerProxy()`` re-introduced. Use "
        "the lazy ``_get_task_manager()`` pattern from "
        "video_analysis.py instead."
    )

    # Lazy helper must exist (same name pattern as video_analysis.py).
    assert "_get_task_manager" in src, (
        "BUG-13-b: stems.py must define a lazy `_get_task_manager()` "
        "helper. Mirror the L-38 fix in video_analysis.py."
    )
