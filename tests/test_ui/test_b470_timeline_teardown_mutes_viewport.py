"""B-470 Stack A regression: timeline scene teardown must not repaint per item.

`TimelineView.load_from_db` clears the QGraphicsScene synchronously on the main
thread (per-item `_scene.removeItem(...)`). Without muting viewport updates each
removal triggers a partial repaint, which blocked the GUI ~7s on project switch
(captured live via perf-watchdog Sampled Stack:
`_on_project_changed -> load_from_db -> clip_items.clear()`).

Source-level guard (CI/local shells may lack Qt). Runtime Qt smoke / live project
switch remains required before marking B-470 Stack A fixed.
"""

from __future__ import annotations

from pathlib import Path


def _load_from_db_teardown_segment() -> str:
    src = Path("ui/timeline.py").read_text(encoding="utf-8")
    body = src.split("def load_from_db", 1)[1].split("def _on_db_load_finished", 1)[0]
    # teardown = everything before the async DB worker is created/started
    return body.split("Hintergrund-Worker", 1)[0]


def test_teardown_mutes_viewport_updates() -> None:
    teardown = _load_from_db_teardown_segment()
    assert "setUpdatesEnabled(False)" in teardown, (
        "B-470 Stack A: synchronous scene teardown must mute viewport updates "
        "(setUpdatesEnabled(False)) so per-item removeItem does not repaint."
    )


def test_teardown_restores_viewport_updates() -> None:
    teardown = _load_from_db_teardown_segment()
    assert "setUpdatesEnabled(True)" in teardown, (
        "B-470 Stack A: viewport updates must be restored after the teardown "
        "(setUpdatesEnabled(True), e.g. in a finally)."
    )


def test_teardown_still_clears_tracked_item_lists() -> None:
    teardown = _load_from_db_teardown_segment()
    # behavior invariant: the same tracked collections are still emptied
    for name in ("clip_items.clear()", "waveform_items.clear()",
                 "cut_lines.clear()", "_beat_markers.clear()"):
        assert name in teardown, f"B-470: teardown must still clear {name}"
