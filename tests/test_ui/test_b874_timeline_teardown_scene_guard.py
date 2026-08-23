"""B-874: Timeline-Teardown darf nur eigene Scene-Items entfernen."""
from __future__ import annotations

import inspect


def test_b874_safe_remove_requires_current_scene_identity() -> None:
    from ui.timeline import InteractiveTimeline

    source = inspect.getsource(InteractiveTimeline.load_from_db)
    helper = source.split("def _safe_rm(_it):", 1)[1].split(
        "for item in self.clip_items:", 1
    )[0]

    validity_guard = "shiboken6.isValid(_it)"
    ownership_guard = "_it.scene() is self._scene"
    remove_call = "self._scene.removeItem(_it)"

    assert validity_guard in helper
    assert ownership_guard in helper
    assert helper.index(validity_guard) < helper.index(ownership_guard)
    assert helper.index(ownership_guard) < helper.index(remove_call)


def test_b874_drop_markers_are_cleared_before_section_membership_is_lost() -> None:
    from ui.timeline import InteractiveTimeline

    source = inspect.getsource(InteractiveTimeline.load_from_db)
    teardown = source.split("# Clear sections + beat grid + drop markers", 1)[1]

    assert teardown.index("self._clear_beat_grid()") < teardown.index(
        "self._clear_sections()"
    )
