"""B-575 regression: timeline scene teardown must not crash on deleted C++ items.

`InteractiveTimeline.load_from_db` clears the QGraphicsScene by iterating Python
lists (`clip_items`, `waveform_items`, `cut_lines`, `_beat_markers`) and calling
`self._scene.removeItem(...)`. On re-entrant / overlapping reloads (Auto-Edit
finish + a fresh "Timeline generieren" shortly after) the scene was already
cleared, so the C++ objects behind still-referenced Python items are deleted ->
`removeItem` raised `RuntimeError("Internal C++ object (...) already deleted.")`
and crashed the app (live-captured 2026-06-24, app_run_2026-06-24_075538).

Source-level guard (CI/local shells may lack Qt). Real runtime proof = GUI live
re-test (Auto-Edit + Timeline generieren repeatedly, no crash dialog).
"""

from __future__ import annotations

from pathlib import Path


def _load_from_db_teardown_segment() -> str:
    src = Path("ui/timeline.py").read_text(encoding="utf-8")
    body = src.split("def load_from_db", 1)[1].split("def _on_db_load_finished", 1)[0]
    # teardown = everything before the async DB worker is created/started
    return body.split("Hintergrund-Worker", 1)[0]


def test_teardown_has_runtimeerror_guard() -> None:
    teardown = _load_from_db_teardown_segment()
    assert "except RuntimeError" in teardown, (
        "B-575: scene teardown must guard removeItem against already-deleted "
        "C++ objects (except RuntimeError), otherwise a stale item crashes the app."
    )


def test_teardown_loops_go_through_guard_not_direct_removeitem() -> None:
    teardown = _load_from_db_teardown_segment()
    # The only place removeItem may be called is inside the guarded helper.
    assert teardown.count("self._scene.removeItem(") == 1, (
        "B-575: the four teardown loops must route through the guarded helper "
        "(_safe_remove); only the helper may call self._scene.removeItem(...)."
    )
    assert "_safe_remove(" in teardown, (
        "B-575: teardown loops must use the guarded _safe_remove(...) helper."
    )


def test_teardown_still_clears_tracked_item_lists() -> None:
    teardown = _load_from_db_teardown_segment()
    # behavior invariant: the same tracked collections are still emptied
    for name in ("clip_items.clear()", "waveform_items.clear()",
                 "cut_lines.clear()", "_beat_markers.clear()"):
        assert name in teardown, f"B-575: teardown must still clear {name}"
