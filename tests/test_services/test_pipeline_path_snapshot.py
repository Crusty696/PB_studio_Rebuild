"""B-150 regression test: pipeline must snapshot project-dependent paths.

Cycle-4 tester: ``_keyframe_dir()`` reads APP_ROOT lazily. If the user
switches projects mid-pipeline, subsequent _keyframe_dir() calls in
the same pipeline return DIFFERENT paths — keyframes get scattered
across two project directories.

Fix: snapshot the keyframe dir at pipeline entry, pass to
extract_keyframes() via output_dir parameter.
"""

from __future__ import annotations

import inspect

from services import video_analysis_service


def test_run_full_pipeline_snapshots_keyframe_dir() -> None:
    src = inspect.getsource(video_analysis_service.run_full_pipeline)
    # Snapshot variable must exist
    assert "pipeline_keyframe_dir" in src or "snapshot" in src.lower(), (
        "BUG-150 regression: run_full_pipeline does not snapshot the "
        "keyframe directory at start. Project-switch mid-run scatters "
        "keyframes across project directories."
    )
    # extract_keyframes must be called with output_dir argument from
    # the snapshot — not just default.
    assert "output_dir=" in src, (
        "BUG-150: extract_keyframes is called without output_dir — it "
        "will fall back to lazy _keyframe_dir() which reads APP_ROOT "
        "live, defeating the snapshot."
    )
