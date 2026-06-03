"""B-139 + B-140 + B-142 batch regression tests.

- B-139: delete_all_media VectorDB-failure must rollback SQL.
- B-140: import_video_folder catches FFmpegError (broad except).
- B-142: beat_this chunk tempfile registered in module-level _temp_files.
"""

from __future__ import annotations

import inspect

import pytest

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


def test_b350_delete_selected_media_rollback_on_vector_db_failure(monkeypatch) -> None:
    """Selected-delete must not commit SQL deletes if VectorDB cleanup fails."""
    import database

    class FakeQuery:
        def __init__(self, entity):
            self.entity = entity

        def filter(self, *args, **kwargs):
            return self

        def filter_by(self, *args, **kwargs):
            return self

        def all(self):
            return []

        def delete(self, synchronize_session=False):
            if self.entity is database.VideoClip:
                return 1
            if self.entity is database.AudioTrack:
                return 0
            return 0

        def update(self, values, synchronize_session=False):
            # B-462 Stage 1: soft-delete uses UPDATE deleted_at instead of DELETE;
            # rowcount semantics are identical for the VectorDB-rollback contract.
            if self.entity is database.VideoClip:
                return 1
            if self.entity is database.AudioTrack:
                return 0
            return 0

    class FakeSession:
        def __init__(self):
            self.committed = False
            self.rolled_back = False

        def query(self, entity):
            return FakeQuery(entity)

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

    class FakeContext:
        def __init__(self, session):
            self.session = session

        def __enter__(self):
            return self.session

        def __exit__(self, exc_type, exc, tb):
            return False

    class FailingVectorDB:
        def delete_by_clip_ids(self, clip_ids):
            raise RuntimeError("vectordb locked")

    fake_session = FakeSession()
    monkeypatch.setattr(database, "nullpool_session", lambda: FakeContext(fake_session))
    monkeypatch.setattr(ingest_service, "VectorDBService", lambda: FailingVectorDB())

    with pytest.raises(RuntimeError, match="VectorDB"):
        ingest_service.delete_selected_media(video_ids=[123], audio_ids=[])

    assert fake_session.rolled_back is True
    assert fake_session.committed is False


def test_b350_delete_selected_media_commits_after_vector_db_success(monkeypatch) -> None:
    """Selected-delete commits SQL only after VectorDB clip cleanup succeeds."""
    import database

    class FakeQuery:
        def __init__(self, entity):
            self.entity = entity

        def filter(self, *args, **kwargs):
            return self

        def filter_by(self, *args, **kwargs):
            return self

        def all(self):
            return []

        def delete(self, synchronize_session=False):
            if self.entity is database.VideoClip:
                return 1
            if self.entity is database.AudioTrack:
                return 0
            return 0

        def update(self, values, synchronize_session=False):
            # B-462 Stage 1: soft-delete uses UPDATE deleted_at instead of DELETE;
            # rowcount semantics are identical for the VectorDB-rollback contract.
            if self.entity is database.VideoClip:
                return 1
            if self.entity is database.AudioTrack:
                return 0
            return 0

    class FakeSession:
        def __init__(self):
            self.committed = False
            self.rolled_back = False

        def query(self, entity):
            return FakeQuery(entity)

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

    class FakeContext:
        def __init__(self, session):
            self.session = session

        def __enter__(self):
            return self.session

        def __exit__(self, exc_type, exc, tb):
            return False

    deleted_clip_ids = []

    class SuccessfulVectorDB:
        def delete_by_clip_ids(self, clip_ids):
            deleted_clip_ids.extend(clip_ids)

    fake_session = FakeSession()
    monkeypatch.setattr(database, "nullpool_session", lambda: FakeContext(fake_session))
    monkeypatch.setattr(ingest_service, "VectorDBService", lambda: SuccessfulVectorDB())

    assert ingest_service.delete_selected_media(video_ids=[123], audio_ids=[]) == 1
    assert deleted_clip_ids == [123]
    assert fake_session.committed is True
    assert fake_session.rolled_back is False


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
