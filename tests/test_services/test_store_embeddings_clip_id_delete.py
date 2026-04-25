"""B-148 regression test: store_embeddings deletes by clip_id, not by path.

Cycle-4 tester: ``vdb.delete_by_video(video_path)`` keys on path
string. If the user renames/moves the file, old embeddings under
the old path stay in VectorDB forever. clip_id is immutable.
"""

from __future__ import annotations

import inspect

from services import video_analysis_service


def test_store_embeddings_uses_delete_by_clip_ids() -> None:
    src = inspect.getsource(video_analysis_service.store_embeddings)
    assert "delete_by_clip_ids" in src, (
        "BUG-148 regression: store_embeddings should call "
        "delete_by_clip_ids([video_clip_id]) — path-based delete leaks "
        "embeddings on file rename."
    )
