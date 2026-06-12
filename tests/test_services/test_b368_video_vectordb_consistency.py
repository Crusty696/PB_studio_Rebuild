from pathlib import Path

import numpy as np
import pytest
from sqlalchemy.orm import Session

from database import Project, VideoClip
from services import video_analysis_service
from services.video_analysis_service import SceneInfo


def test_b368_store_embeddings_raises_when_old_clip_delete_fails(monkeypatch):
    calls = {"add": 0}

    class _FailingDeleteVectorDB:
        def count(self):
            return 3

        def delete_by_clip_ids(self, _clip_ids):
            raise RuntimeError("vector db locked")

        def add_embeddings_batch(self, _clip_id, _entries):
            calls["add"] += 1

    monkeypatch.setattr(
        "services.vector_db_service.VectorDBService",
        lambda: _FailingDeleteVectorDB(),
    )

    scenes = [
        SceneInfo(index=0, start_time=0.0, end_time=1.0, embedding=np.ones(4, dtype=np.float32)),
    ]

    with pytest.raises(RuntimeError, match="VectorDB"):
        video_analysis_service.store_embeddings("clip.mp4", scenes, video_clip_id=368)

    assert calls["add"] == 0


def test_b368_run_full_pipeline_does_not_write_vectordb_before_scene_db_commit(monkeypatch, test_engine, tmp_path: Path):
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"fake-video")
    calls = {"store_embeddings": 0}
    scenes = [SceneInfo(index=0, start_time=0.0, end_time=1.0, embedding=np.ones(4, dtype=np.float32))]
    with Session(test_engine) as session:
        project = Project(name="p", path=str(tmp_path))
        session.add(project)
        session.flush()
        clip = VideoClip(project_id=project.id, file_path=str(source))
        session.add(clip)
        session.commit()
        clip_id = clip.id

    monkeypatch.setattr(video_analysis_service, "_keyframe_dir", lambda: tmp_path / "keyframes")
    monkeypatch.setattr(video_analysis_service, "detect_scenes", lambda *_a, **_k: scenes)
    monkeypatch.setattr(video_analysis_service, "compute_motion_scores", lambda _path, s, **_k: s)
    monkeypatch.setattr(video_analysis_service, "extract_keyframes", lambda _path, s, **_k: s)
    monkeypatch.setattr(video_analysis_service, "generate_embeddings", lambda s, **_k: s)
    monkeypatch.setattr(video_analysis_service, "_run_structure_enrichment", lambda _clip_id: None)
    monkeypatch.setattr(video_analysis_service.analysis_status_service, "mark_started", lambda *_a, **_k: None)
    monkeypatch.setattr(video_analysis_service.analysis_status_service, "mark_done", lambda *_a, **_k: None)
    monkeypatch.setattr(video_analysis_service.analysis_status_service, "mark_error", lambda *_a, **_k: None)

    def _failing_scene_store(_clip_id, _scenes, **_kwargs):
        # **_kwargs: B-490 Followup (CRF-005) erweitert store_scenes_in_db
        # um expected_db_url — Mock muss die neue Signatur akzeptieren.
        raise RuntimeError("sqlite commit failed")

    def _store_embeddings(*_args, **_kwargs):
        calls["store_embeddings"] += 1
        return 1

    monkeypatch.setattr(video_analysis_service, "store_scenes_in_db", _failing_scene_store)
    monkeypatch.setattr(video_analysis_service, "store_embeddings", _store_embeddings)

    with pytest.raises(RuntimeError, match="sqlite commit failed"):
        video_analysis_service.run_full_pipeline(str(source), video_clip_id=clip_id, defer_captioning=True)

    assert calls["store_embeddings"] == 0
