from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy.orm import Session

from database import Project, TimelineEntry, TimelineSnapshot


def test_pycache_cleanup_refuses_rglob_result_outside_project(monkeypatch, tmp_path: Path):
    import start_pb_studio

    project_root = tmp_path / "repo"
    outside = tmp_path / "outside" / "__pycache__"
    project_root.mkdir()
    outside.mkdir(parents=True)

    class _FakeProjectDir(type(project_root)):
        def rglob(self, pattern):
            assert pattern == "__pycache__"
            return [outside]

    fake_project_root = _FakeProjectDir(project_root)
    removed: list[Path] = []

    monkeypatch.setattr(start_pb_studio, "PROJECT_DIR", fake_project_root)
    monkeypatch.setattr(start_pb_studio.shutil, "rmtree", lambda path, ignore_errors=False: removed.append(Path(path)))

    start_pb_studio._cleanup_pycache()

    assert removed == []


def test_save_as_cleanup_refuses_project_parent_target(tmp_path: Path):
    from services.project_manager import ProjectManager

    source = tmp_path / "source_project"
    source.mkdir()

    with pytest.raises(ValueError, match="Refusing"):
        ProjectManager._cleanup_failed_save_as(source, source.parent)

    assert source.exists()
    assert source.parent.exists()


def test_vector_delete_by_clip_ids_keeps_other_clip_embeddings(tmp_path: Path):
    import services.vector_db_service as vector_db_service

    vector_db_service._instance = None
    db_path = tmp_path / "vector" / "embeddings.db"
    service = vector_db_service.VectorDBService(db_path)

    emb_a = np.ones(vector_db_service.EMBEDDING_DIM, dtype=np.float32)
    emb_b = np.full(vector_db_service.EMBEDDING_DIM, 2.0, dtype=np.float32)
    service.add_embedding(clip_id=1, video_path="clip1.mp4", scene_index=0, scene_start=0.0, scene_end=1.0, embedding=emb_a)
    service.add_embedding(clip_id=2, video_path="clip2.mp4", scene_index=0, scene_start=0.0, scene_end=1.0, embedding=emb_b)

    service.delete_by_clip_ids([1])
    _matrix, metadata = service.get_all_embeddings()

    assert [m["id"] for m in metadata] == [2_000_000]
    assert metadata[0]["video_path"] == "clip2.mp4"

    vector_db_service._instance = None


def test_restore_snapshot_clears_only_snapshot_project(test_engine, monkeypatch):
    import services.timeline_snapshot_service as timeline_snapshot_service

    monkeypatch.setattr(timeline_snapshot_service, "engine", test_engine)

    with Session(test_engine) as session:
        p1 = Project(name="P1", path=".")
        p2 = Project(name="P2", path=".")
        session.add_all([p1, p2])
        session.flush()
        old_p1 = TimelineEntry(project_id=p1.id, track="video", media_id=1, start_time=0.0, end_time=1.0)
        keep_p2 = TimelineEntry(project_id=p2.id, track="video", media_id=2, start_time=0.0, end_time=1.0)
        session.add_all([old_p1, keep_p2])
        session.flush()
        snap = TimelineSnapshot(
            project_id=p1.id,
            version=1,
            label="restore-p1",
            payload_json=json.dumps([
                {
                    "track": "video",
                    "media_id": 3,
                    "start": 5.0,
                    "end": 6.0,
                    "lane": 0,
                    "source_start": 0.0,
                    "source_end": 1.0,
                    "locked": False,
                }
            ]),
        )
        session.add(snap)
        session.commit()
        snap_id = snap.id
        p1_id = p1.id
        p2_id = p2.id

    timeline_snapshot_service.restore_snapshot(snap_id)

    with Session(test_engine) as session:
        p1_entries = session.query(TimelineEntry).filter_by(project_id=p1_id).all()
        p2_entries = session.query(TimelineEntry).filter_by(project_id=p2_id).all()

    assert [(e.media_id, e.start_time, e.end_time) for e in p1_entries] == [(3, 5.0, 6.0)]
    assert [(e.media_id, e.start_time, e.end_time) for e in p2_entries] == [(2, 0.0, 1.0)]
