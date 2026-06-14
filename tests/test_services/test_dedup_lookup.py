from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import AnalysisArtifact, AnalysisJob, Base
from services.storage_provenance.dedup_lookup import check_dedup, stable_params_hash


def test_stable_params_hash_sorts_dict_keys() -> None:
    assert stable_params_hash({"b": 2, "a": 1}) == stable_params_hash({"a": 1, "b": 2})


def test_dedup_lookup_returns_hit_with_artifacts() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    params = {"quality": "high", "batch": 1}
    with Session(engine) as session:
        job = AnalysisJob(
            source_sha256="a" * 64,
            step_id="audio.v2.stems",
            step_version="1",
            params_hash=stable_params_hash(params),
            status="done",
        )
        job.artifacts.append(
            AnalysisArtifact(
                artifact_type="stem",
                artifact_role="vocals_stem",
                path="audio/stems/vocals.flac",
            )
        )
        session.add(job)
        session.commit()

        result = check_dedup(session, "a" * 64, "audio.v2.stems", "1", params)

    assert result.state == "hit"
    assert result.artifacts["vocals_stem"] == "audio/stems/vocals.flac"


def test_dedup_lookup_returns_partial_for_partial_job() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    params = {"quality": "high"}

    with Session(engine) as session:
        session.add(
            AnalysisJob(
                source_sha256="b" * 64,
                step_id="video.raft",
                step_version="1",
                params_hash=stable_params_hash(params),
                status="partial",
            )
        )
        session.commit()

        result = check_dedup(session, "b" * 64, "video.raft", "1", params)

    assert result.state == "partial"
