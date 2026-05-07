"""B-275 regression: large timeline scene builds must not block one MetaCall."""

from __future__ import annotations

from pathlib import Path


def test_timeline_db_load_uses_batched_scene_build() -> None:
    """B-275: worker-finished MetaCall must schedule scene build in batches.

    This is a source-level guard because CI/local shells may not have Qt.
    Runtime Qt smoke remains required before marking B-275 fixed.
    """
    src = Path("ui/timeline.py").read_text(encoding="utf-8")

    assert "_BUILD_BATCH_SIZE" in src, (
        "B-275: timeline scene build needs an explicit batch size."
    )
    assert "_start_batched_entry_build" in src
    assert "_build_entry_batch" in src
    assert "QTimer.singleShot(0, self._build_entry_batch)" in src, (
        "B-275: next scene-build chunk must be yielded via Qt event loop."
    )

    on_finished = src.split("def _on_db_load_finished", 1)[1].split(
        "def _build_entries", 1
    )[0]
    assert "self._build_entries(" not in on_finished, (
        "B-275: _on_db_load_finished must not synchronously build all items "
        "inside one worker-finished MetaCall."
    )
