from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import AnalysisArtifact, AnalysisJob, Base
from services.storage_provenance.adapter_layer import resolve_artifact_path


def test_adapter_resolves_source_sha_artifact_from_provenance(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    artifact = storage_root / "by_sha" / "aa" / ("a" * 64) / "audio" / "stems" / "vocals.flac"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"vocals")

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        job = AnalysisJob(
            source_sha256="a" * 64,
            step_id="audio.v2.stems",
            step_version="1",
            params_hash="p",
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

        resolved = resolve_artifact_path(session, "a" * 64, "vocals_stem", storage_root=storage_root)

    assert resolved == artifact


def test_adapter_falls_back_to_legacy_track_stem_path(tmp_path: Path) -> None:
    legacy_root = tmp_path / "project" / "storage" / "stems"
    legacy_stem = legacy_root / "42" / "vocals.flac"
    legacy_stem.parent.mkdir(parents=True)
    legacy_stem.write_bytes(b"legacy")

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        resolved = resolve_artifact_path(
            session,
            42,
            "vocals_stem",
            storage_root=tmp_path / "global",
            legacy_stems_root=legacy_root,
        )

    assert resolved == legacy_stem
