from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from database import AnalysisArtifact, AnalysisJob, Base, Project, ProjectSource
from services.storage_provenance.storage_browser import StorageBrowserService


def _add_job(
    session: Session,
    *,
    sha: str,
    step: str,
    status: str,
    finished_at: datetime,
    artifact_bytes: list[int | None],
) -> None:
    job = AnalysisJob(
        source_sha256=sha,
        step_id=step,
        step_version="1",
        params_hash=f"params-{sha[:4]}-{step}",
        status=status,
        finished_at=finished_at,
    )
    for index, bytes_ in enumerate(artifact_bytes):
        job.artifacts.append(AnalysisArtifact(
            artifact_type="bin",
            artifact_role=f"{step}-{index}",
            path=f"{step}/{index}.bin",
            bytes=bytes_,
        ))
    session.add(job)


def test_e8_list_sources_is_identical_with_exactly_three_bulk_selects(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sha_a = "a" * 64
    sha_b = "b" * 64
    sha_c = "c" * 64
    newer = datetime(2026, 7, 1, 12, 0)
    older = datetime(2026, 6, 1, 12, 0)

    with Session(engine) as session:
        session.add_all([
            Project(id=1, name="Zulu", path=str(tmp_path / "z")),
            Project(id=2, name="Alpha", path=str(tmp_path / "a")),
        ])
        session.add_all([
            ProjectSource(
                project_id=1,
                source_sha256=sha_a,
                current_source_path=str(tmp_path / "new.wav"),
                last_seen_at=newer,
            ),
            ProjectSource(
                project_id=2,
                source_sha256=sha_a,
                current_source_path=str(tmp_path / "new.wav"),
                last_seen_at=newer,
            ),
            ProjectSource(
                project_id=1,
                source_sha256=sha_b,
                current_source_path=str(tmp_path / "old.mp4"),
                last_seen_at=older,
            ),
        ])
        _add_job(
            session,
            sha=sha_a,
            step="audio.stems",
            status="done",
            finished_at=newer,
            artifact_bytes=[100, 25],
        )
        _add_job(
            session,
            sha=sha_a,
            step="audio.waveform",
            status="failed",
            finished_at=newer,
            artifact_bytes=[50],
        )
        _add_job(
            session,
            sha=sha_b,
            step="video.outputs",
            status="done",
            finished_at=older,
            artifact_bytes=[200],
        )
        _add_job(
            session,
            sha=sha_c,
            step="orphan.step",
            status="done",
            finished_at=older,
            artifact_bytes=[None],
        )
        session.commit()

        statements: list[str] = []

        def _before(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", _before)
        try:
            rows = StorageBrowserService(session).list_sources()
        finally:
            event.remove(engine, "before_cursor_execute", _before)

    assert [
        (
            row.source_sha256,
            row.file_name,
            row.projects_used_by,
            row.project_count,
            row.stages_done,
            row.total_bytes,
            row.last_used,
        )
        for row in rows
    ] == [
        (sha_a, "new.wav", "Alpha, Zulu", 2, 1, 175, newer),
        (sha_c, "-", "-", 0, 1, 0, older),
        (sha_b, "old.mp4", "Zulu", 1, 1, 200, older),
    ]
    selects = [
        statement for statement in statements
        if statement.lstrip().upper().startswith("SELECT")
    ]
    assert len(selects) == 3, selects
