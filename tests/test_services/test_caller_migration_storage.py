from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import AnalysisArtifact, AnalysisJob, AudioTrack, Base, Project, ProjectSource, VideoClip
from services.storage_provenance.source_identity import compute_source_sha256


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_provenance_recorder_upserts_job_and_artifacts(tmp_path: Path) -> None:
    from services.storage_provenance.caller_migration import ProvenanceRecorder

    source = tmp_path / "track.wav"
    source.write_bytes(b"audio")
    artifact = tmp_path / "vocals.wav"
    artifact.write_bytes(b"vocals")

    with _session() as session:
        session.add(Project(id=1, name="P", path=str(tmp_path), resolution="1920x1080", fps=30.0))
        session.commit()
        recorder = ProvenanceRecorder(session)

        first = recorder.record_done(
            project_id=1,
            source_path=source,
            media_type="audio",
            step_id="audio.v2.stems",
            params={"stage": "stem_gen"},
            artifacts={"vocals_stem": artifact},
        )
        second = recorder.record_done(
            project_id=1,
            source_path=source,
            media_type="audio",
            step_id="audio.v2.stems",
            params={"stage": "stem_gen"},
            artifacts={"vocals_stem": artifact},
        )

        source_sha = compute_source_sha256(source, media_type="audio", mode="strict")

        assert first.dedup_state == "miss"
        assert second.dedup_state == "hit"
        assert session.query(ProjectSource).filter_by(source_sha256=source_sha).count() == 1
        assert session.query(AnalysisJob).filter_by(source_sha256=source_sha, step_id="audio.v2.stems").count() == 1
        assert session.query(AnalysisArtifact).filter_by(artifact_role="vocals_stem").one().sha256 is not None


def test_audio_stem_stage_writes_provenance_job(monkeypatch, tmp_path: Path) -> None:
    import services.audio_pipeline.stages as stages
    from services.audio_pipeline.context import PipelineContext

    source = tmp_path / "track.wav"
    source.write_bytes(b"audio")
    session = _session()
    session.add(Project(id=1, name="P", path=str(tmp_path), resolution="1920x1080", fps=30.0))
    session.add(AudioTrack(id=7, project_id=1, file_path=str(source)))
    session.commit()

    @contextmanager
    def fake_nullpool_session():
        yield session

    class FakeSeparator:
        def separate_to(self, file_path: str, out_dir: str, subtype: str):
            root = Path(out_dir)
            root.mkdir(parents=True, exist_ok=True)
            result = {}
            for name in ("vocals", "drums", "bass", "other"):
                path = root / f"{name}.wav"
                path.write_bytes(name.encode("utf-8"))
                result[name] = str(path)
            return result

    monkeypatch.setattr(stages, "nullpool_session", fake_nullpool_session)
    stage = stages.StemGenStage(separator_cls=FakeSeparator)
    stage._stems_root = tmp_path / "stems"
    context = PipelineContext(track_id=7, original_path=str(source))

    stage.run(context)

    source_sha = compute_source_sha256(source, media_type="audio", mode="strict")
    job = session.query(AnalysisJob).filter_by(source_sha256=source_sha, step_id="audio.v2.stems").one()
    artifacts = session.query(AnalysisArtifact).filter_by(job_id=job.id).all()

    assert len(artifacts) == 4
    assert {artifact.artifact_role for artifact in artifacts} == {
        "vocals_stem",
        "drums_stem",
        "bass_stem",
        "other_stem",
    }


def test_video_pipeline_done_stage_writes_provenance_job(monkeypatch, tmp_path: Path) -> None:
    import services.video_pipeline.orchestrator as orchestrator
    from services.video_pipeline.stages.base import StageResult

    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")
    session = _session()
    session.add(Project(id=1, name="P", path=str(tmp_path), resolution="1920x1080", fps=30.0))
    session.add(VideoClip(id=42, project_id=1, file_path=str(source)))
    session.commit()

    @contextmanager
    def fake_nullpool_session():
        yield session

    class FakeStage:
        stage_id = "scene_detect"

        def run(self, source_path, storage_dir, *, cancel_token=None):
            artifact = Path(storage_dir) / "scenes.json"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("[]")
            return StageResult(
                stage_id=self.stage_id,
                status="done",
                duration_s=0.01,
                artifacts={"scenes_json": artifact},
            )

    monkeypatch.setattr(orchestrator, "nullpool_session", fake_nullpool_session)
    pipe = orchestrator.VideoAnalysisPipeline(
        track_id=42,
        source_path=source,
        storage_dir=tmp_path / "video-storage",
        stages=[FakeStage()],
    )

    pipe.run()

    source_sha = compute_source_sha256(source, media_type="video", mode="strict")
    job = session.query(AnalysisJob).filter_by(source_sha256=source_sha, step_id="video.scene_detect").one()
    artifact = session.query(AnalysisArtifact).filter_by(job_id=job.id).one()
    assert artifact.artifact_role == "scenes_json"
