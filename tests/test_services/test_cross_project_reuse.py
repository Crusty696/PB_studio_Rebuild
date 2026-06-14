from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import AnalysisJob, AnalysisStatus, Base, Project, ProjectSource
from services.storage_provenance.cross_project_reuse import (
    apply_cross_project_reuse_status,
    lookup_cross_project_reuse,
)
from services.storage_provenance.source_identity import compute_source_sha256


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_lookup_cross_project_reuse_returns_previous_project_and_tooltip(tmp_path: Path) -> None:
    source = tmp_path / "track.wav"
    source.write_bytes(b"same audio bytes")
    source_sha = compute_source_sha256(source, media_type="audio", mode="strict")

    with _session() as session:
        session.add(Project(id=1, name="Projekt A", path=str(tmp_path / "a"), resolution="1920x1080", fps=30.0))
        session.add(Project(id=2, name="Projekt B", path=str(tmp_path / "b"), resolution="1920x1080", fps=30.0))
        session.add(
            ProjectSource(
                project_id=1,
                source_sha256=source_sha,
                current_source_path=str(source),
                last_seen_at=datetime(2026, 6, 14, 12, 0, 0),
            )
        )
        session.add(
            AnalysisJob(
                source_sha256=source_sha,
                step_id="audio.v2.stems",
                step_version="1",
                params_hash="legacy-v2-stems",
                status="done",
                produced_by_model="Demucs",
                finished_at=datetime(2026, 6, 14, 13, 0, 0),
            )
        )
        session.commit()

        result = lookup_cross_project_reuse(
            session,
            source,
            media_type="audio",
            current_project_id=2,
        )

    assert result is not None
    assert result.project_name == "Projekt A"
    assert result.toast_message == (
        "Datei wurde bereits in Projekt Projekt A analysiert. Ergebnisse werden mitverwendet."
    )
    assert result.steps[0].analysis_step_key == "stem_separation"
    assert result.steps[0].tooltip == "Erzeugt am 2026-06-14 13:00 in Projekt Projekt A, Modell Demucs"


def test_apply_cross_project_reuse_status_marks_reused_step_done(tmp_path: Path) -> None:
    source = tmp_path / "track.wav"
    source.write_bytes(b"same audio bytes")
    source_sha = compute_source_sha256(source, media_type="audio", mode="strict")

    with _session() as session:
        session.add(Project(id=1, name="Projekt A", path=str(tmp_path / "a"), resolution="1920x1080", fps=30.0))
        session.add(Project(id=2, name="Projekt B", path=str(tmp_path / "b"), resolution="1920x1080", fps=30.0))
        session.add(ProjectSource(project_id=1, source_sha256=source_sha, current_source_path=str(source)))
        session.add(
            AnalysisJob(
                source_sha256=source_sha,
                step_id="audio.v2.stems",
                step_version="1",
                params_hash="legacy-v2-stems",
                status="done",
                produced_by_model="Demucs",
                finished_at=datetime(2026, 6, 14, 13, 0, 0),
            )
        )
        session.commit()

        result = apply_cross_project_reuse_status(
            session,
            source,
            media_type="audio",
            media_id=99,
            current_project_id=2,
        )

        status = (
            session.query(AnalysisStatus)
            .filter_by(media_type="audio", media_id=99, step_key="stem_separation")
            .one()
        )

    assert result is not None
    assert status.status == "done"
    assert status.value_summary["reuse_source_project"] == "Projekt A"
    assert status.value_summary["provenance_tooltip"] == (
        "Erzeugt am 2026-06-14 13:00 in Projekt Projekt A, Modell Demucs"
    )


def test_lookup_cross_project_reuse_ignores_current_project_only_hit(tmp_path: Path) -> None:
    source = tmp_path / "track.wav"
    source.write_bytes(b"same audio bytes")
    source_sha = compute_source_sha256(source, media_type="audio", mode="strict")

    with _session() as session:
        session.add(Project(id=2, name="Projekt B", path=str(tmp_path / "b"), resolution="1920x1080", fps=30.0))
        session.add(ProjectSource(project_id=2, source_sha256=source_sha, current_source_path=str(source)))
        session.add(
            AnalysisJob(
                source_sha256=source_sha,
                step_id="audio.v2.stems",
                step_version="1",
                params_hash="legacy-v2-stems",
                status="done",
            )
        )
        session.commit()

        result = lookup_cross_project_reuse(session, source, media_type="audio", current_project_id=2)

    assert result is None
