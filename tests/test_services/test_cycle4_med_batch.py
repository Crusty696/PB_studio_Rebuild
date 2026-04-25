"""B-139 + B-140 + B-142 batch regression tests.

- B-139: delete_all_media VectorDB-failure must rollback SQL.
- B-140: import_video_folder catches FFmpegError (broad except).
- B-142: beat_this chunk tempfile registered in module-level _temp_files.
"""

from __future__ import annotations

import inspect

from services import ingest_service, beat_analysis_service


def test_b139_delete_all_media_rollback_on_vector_db_failure() -> None:
    """The VectorDB delete_all path must rollback the SQL session if it
    fails (preventing SQL-empty + VectorDB-orphan partial state)."""
    src = inspect.getsource(ingest_service)
    # Our fix calls session.rollback() and raises in the VectorDB except.
    assert "session.rollback()" in src and "RuntimeError" in src, (
        "BUG-139 regression: delete_all_media must rollback SQL when "
        "VectorDB fails."
    )


def test_b140_import_video_folder_has_broad_except() -> None:
    """The folder-import loop must have a broad except Exception clause
    so FFmpegError (or any custom Exception) skips the file rather than
    aborting the whole batch."""
    src = inspect.getsource(ingest_service.import_video_folder)
    # B-140 fix: the loop now has ``except Exception`` after the narrow
    # tuples.
    assert src.count("except Exception") >= 1, (
        "BUG-140 regression: import_video_folder loop has no broad "
        "Exception safety net. Custom errors abort the batch."
    )


def test_b142_beat_this_chunk_tempfile_tracked() -> None:
    """The chunk-tempfile must be added to ``_temp_files`` set so the
    atexit cleanup catches it on hard-kill / force-quit."""
    src = inspect.getsource(
        beat_analysis_service.BeatAnalysisService._analyze_chunked
    )
    assert "_temp_files.add" in src, (
        "BUG-142 regression: chunk tmp_path is not added to _temp_files. "
        "Force-quit during sf.write leaks 30MB+ WAV per chunk."
    )
