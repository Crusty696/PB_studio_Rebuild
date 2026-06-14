from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import AnalysisArtifact, AudioTrack, Base, Project
from services.storage_provenance.schnitt_audio_adapter import (
    default_global_storage_root,
    ensure_schnitt_audio_adapter,
)


def test_schnitt_audio_adapter_builds_missing_stem_junction(tmp_path: Path) -> None:
    source = tmp_path / "track.wav"
    source.write_bytes(b"audio-source")
    stem_dir = tmp_path / "project" / "storage" / "stems" / "1"
    stem_dir.mkdir(parents=True)
    (stem_dir / "vocals.flac").write_bytes(b"vocals")

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Project(id=1, name="p", path=str(tmp_path / "project"), resolution="1920x1080", fps=30.0))
        session.add(
            AudioTrack(
                id=1,
                project_id=1,
                file_path=str(source),
                stem_vocals_path=str(stem_dir / "vocals.flac"),
            )
        )
        session.commit()

        result = ensure_schnitt_audio_adapter(session, storage_root=tmp_path / "global")
        artifact = session.query(AnalysisArtifact).filter_by(artifact_role="vocals_stem").one()

    assert result.audio_tracks == 1
    assert artifact.path == "audio/stems/vocals.flac"


def test_schnitt_audio_adapter_is_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "track.wav"
    source.write_bytes(b"audio-source")
    stem_dir = tmp_path / "project" / "storage" / "stems" / "1"
    stem_dir.mkdir(parents=True)
    (stem_dir / "vocals.flac").write_bytes(b"vocals")

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Project(id=1, name="p", path=str(tmp_path / "project"), resolution="1920x1080", fps=30.0))
        session.add(
            AudioTrack(
                id=1,
                project_id=1,
                file_path=str(source),
                stem_vocals_path=str(stem_dir / "vocals.flac"),
            )
        )
        session.commit()

        ensure_schnitt_audio_adapter(session, storage_root=tmp_path / "global")
        ensure_schnitt_audio_adapter(session, storage_root=tmp_path / "global")

        assert session.query(AnalysisArtifact).filter_by(artifact_role="vocals_stem").count() == 1


def test_default_global_storage_root_uses_appdata(monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", r"C:\Users\tester\AppData\Roaming")

    assert default_global_storage_root() == Path(r"C:\Users\tester\AppData\Roaming") / "PBStudio" / "storage"


def test_default_global_storage_root_falls_back_to_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert default_global_storage_root() == tmp_path / ".PBStudio" / "storage"
