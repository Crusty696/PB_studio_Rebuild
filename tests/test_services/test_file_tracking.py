from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import Base, Project, ProjectSource
from services.storage_provenance.file_tracking import repair_missing_sources
from services.storage_provenance.source_identity import compute_source_sha256


def test_file_tracking_repairs_moved_source_path(tmp_path: Path) -> None:
    original = tmp_path / "old" / "track.wav"
    moved = tmp_path / "library" / "track.wav"
    original.parent.mkdir()
    moved.parent.mkdir()
    moved.write_bytes(b"audio-data")

    source_sha = compute_source_sha256(moved, media_type="audio", mode="strict")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(Project(id=1, name="p", path=str(tmp_path), resolution="1920x1080", fps=30.0))
        session.add(
            ProjectSource(
                project_id=1,
                source_sha256=source_sha,
                current_source_path=str(original),
            )
        )
        session.commit()

        result = repair_missing_sources(session, search_roots=[moved.parent], media_type="audio")
        repaired = session.query(ProjectSource).one()

    assert result.repaired == 1
    assert Path(repaired.current_source_path) == moved


def test_file_tracking_reports_missing_and_skips_existing_sources(tmp_path: Path) -> None:
    existing = tmp_path / "existing.wav"
    existing.write_bytes(b"audio-data")
    missing = tmp_path / "missing.wav"

    existing_sha = compute_source_sha256(existing, media_type="audio", mode="strict")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(Project(id=1, name="p", path=str(tmp_path), resolution="1920x1080", fps=30.0))
        session.add(
            ProjectSource(
                id=1,
                project_id=1,
                source_sha256=existing_sha,
                current_source_path=str(existing),
            )
        )
        session.add(
            ProjectSource(
                id=2,
                project_id=1,
                source_sha256="0" * 64,
                current_source_path=str(missing),
            )
        )
        session.commit()

        result = repair_missing_sources(session, search_roots=[tmp_path / "does-not-exist"], media_type="audio")

    assert result.checked == 2
    assert result.repaired == 0
    assert result.missing == (2,)


def test_project_open_repair_scans_project_folder_only(tmp_path: Path) -> None:
    from services.project_manager import repair_missing_sources_on_project_open

    original = tmp_path / "old" / "track.wav"
    moved = tmp_path / "media" / "track.wav"
    moved.parent.mkdir()
    moved.write_bytes(b"audio-data")

    source_sha = compute_source_sha256(moved, media_type="audio", mode="strict")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(Project(id=1, name="p", path=str(tmp_path), resolution="1920x1080", fps=30.0))
        session.add(
            Project(
                id=2,
                name="other",
                path=str(tmp_path / "other-project"),
                resolution="1920x1080",
                fps=30.0,
            )
        )
        session.add(
            ProjectSource(
                id=1,
                project_id=1,
                source_sha256=source_sha,
                current_source_path=str(original),
            )
        )
        session.add(
            ProjectSource(
                id=2,
                project_id=2,
                source_sha256="1" * 64,
                current_source_path=str(tmp_path / "other-missing.wav"),
            )
        )
        session.commit()

        result = repair_missing_sources_on_project_open(session, tmp_path)
        repaired = session.query(ProjectSource).filter(ProjectSource.id == 1).one()
        other = session.query(ProjectSource).filter(ProjectSource.id == 2).one()

    assert result == {"checked": 1, "repaired": 1, "missing": 0}
    assert Path(repaired.current_source_path) == moved
    assert Path(other.current_source_path) == tmp_path / "other-missing.wav"
