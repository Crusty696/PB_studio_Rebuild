from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy.orm import Session

from database import Project, VideoClip
from services import video_analysis_service


def test_b369_run_full_pipeline_rejects_soft_deleted_clip(monkeypatch, test_engine, tmp_path: Path):
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"fake-video")
    with Session(test_engine) as session:
        project = Project(name="p", path=str(tmp_path))
        session.add(project)
        session.flush()
        clip = VideoClip(project_id=project.id, file_path=str(source), deleted_at=datetime.utcnow())
        session.add(clip)
        session.commit()
        clip_id = clip.id

    calls = {"detect": 0}
    monkeypatch.setattr(video_analysis_service, "_keyframe_dir", lambda: tmp_path / "keyframes")

    def _detect(*_args, **_kwargs):
        calls["detect"] += 1
        return []

    monkeypatch.setattr(video_analysis_service, "detect_scenes", _detect)

    with pytest.raises(ValueError, match="geloescht|deleted|nicht gefunden"):
        video_analysis_service.run_full_pipeline(str(source), video_clip_id=clip_id)

    assert calls["detect"] == 0


def test_b369_search_videos_by_text_filters_soft_deleted_vector_hits(monkeypatch, test_engine, tmp_path: Path):
    with Session(test_engine) as session:
        project = Project(name="p", path=str(tmp_path))
        session.add(project)
        session.flush()
        clip = VideoClip(project_id=project.id, file_path="deleted.mp4", deleted_at=datetime.utcnow())
        session.add(clip)
        session.commit()
        clip_id = clip.id

    monkeypatch.setattr(video_analysis_service, "text_to_embedding", lambda _query: np.ones(4, dtype=np.float32))

    class _FakeVectorDB:
        def search(self, *_args, **_kwargs):
            return [{"id": clip_id * 1_000_000, "video_path": "deleted.mp4", "scene_index": 0}]

    monkeypatch.setattr("services.vector_db_service.VectorDBService", lambda: _FakeVectorDB())

    assert video_analysis_service.search_videos_by_text("deleted", top_k=5) == []


def test_b369_create_proxy_action_does_not_queue_soft_deleted_clip(monkeypatch, test_engine, tmp_path: Path):
    from services.actions import video_actions

    with Session(test_engine) as session:
        project = Project(name="p", path=str(tmp_path))
        session.add(project)
        session.flush()
        clip = VideoClip(project_id=project.id, file_path="deleted.mp4", deleted_at=datetime.utcnow())
        session.add(clip)
        session.commit()
        clip_id = clip.id

    class _Signal:
        def __init__(self):
            self.emits = []

        def emit(self, *args):
            self.emits.append(args)

    class _TaskManager:
        def __init__(self):
            self.agent_command_signal = _Signal()

    tm = _TaskManager()
    monkeypatch.setattr(video_actions, "_get_task_manager", lambda: tm)

    result = video_actions.create_proxy_action(clip_id=clip_id)

    assert "error" in result
    assert tm.agent_command_signal.emits == []
