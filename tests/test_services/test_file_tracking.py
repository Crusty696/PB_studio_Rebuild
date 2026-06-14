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
