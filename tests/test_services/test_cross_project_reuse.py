from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import (
    AnalysisJob,
    AnalysisStatus,
    AudioTrack,
    Base,
    Project,
    ProjectSource,
)
from services.storage_provenance.cross_project_reuse import (
    apply_cross_project_reuse_status,
    lookup_cross_project_reuse,
)
from services.storage_provenance.source_identity import compute_source_sha256


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_artifact(storage_root, source_sha) -> None:
    """B-544: place a real artifact file so reuse is considered valid (the
    manifest alone is not enough; the underlying stems must still exist)."""
    from services.storage_provenance.layout import StorageLayout

    art = StorageLayout(storage_root).source_root(source_sha) / "audio" / "stems" / "drums.wav"
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_bytes(b"stem-bytes")


def _seed_stem_artifacts(storage_root, source_sha) -> dict[str, Path]:
    from services.storage_provenance.layout import StorageLayout

    stem_dir = StorageLayout(storage_root).source_root(source_sha) / "audio" / "stems"
    stem_dir.mkdir(parents=True, exist_ok=True)
    result = {}
    for name in ("vocals", "drums", "bass", "other"):
        path = stem_dir / f"{name}.wav"
        path.write_bytes(f"{name}-stem".encode())
        result[name] = path.resolve()
    return result


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

    storage_root = tmp_path / "storage"
    expected_stems = _seed_stem_artifacts(storage_root, source_sha)

    with _session() as session:
        session.add(Project(id=1, name="Projekt A", path=str(tmp_path / "a"), resolution="1920x1080", fps=30.0))
        session.add(Project(id=2, name="Projekt B", path=str(tmp_path / "b"), resolution="1920x1080", fps=30.0))
        session.add(AudioTrack(id=99, project_id=2, file_path=str(source), title="Track"))
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
            storage_root=storage_root,
        )

        status = (
            session.query(AnalysisStatus)
            .filter_by(media_type="audio", media_id=99, step_key="stem_separation")
            .one()
        )
        track = session.get(AudioTrack, 99)

    assert result is not None
    assert status.status == "done"
    assert status.value_summary["reuse_source_project"] == "Projekt A"
    assert status.value_summary["provenance_tooltip"] == (
        "Erzeugt am 2026-06-14 13:00 in Projekt Projekt A, Modell Demucs"
    )
    assert Path(track.stem_vocals_path) == expected_stems["vocals"]
    assert Path(track.stem_drums_path) == expected_stems["drums"]
    assert Path(track.stem_bass_path) == expected_stems["bass"]
    assert Path(track.stem_other_path) == expected_stems["other"]


def test_apply_cross_project_reuse_does_not_mark_incomplete_stems_done(
    tmp_path: Path,
) -> None:
    source = tmp_path / "track.wav"
    source.write_bytes(b"same audio bytes")
    source_sha = compute_source_sha256(source, media_type="audio", mode="strict")
    storage_root = tmp_path / "storage"
    _seed_artifact(storage_root, source_sha)  # only drums.wav

    with _session() as session:
        session.add(Project(id=1, name="Projekt A", path=str(tmp_path / "a"), resolution="1920x1080", fps=30.0))
        session.add(Project(id=2, name="Projekt B", path=str(tmp_path / "b"), resolution="1920x1080", fps=30.0))
        session.add(AudioTrack(id=99, project_id=2, file_path=str(source), title="Track"))
        session.add(ProjectSource(project_id=1, source_sha256=source_sha, current_source_path=str(source)))
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

        result = apply_cross_project_reuse_status(
            session,
            source,
            media_type="audio",
            media_id=99,
            current_project_id=2,
            storage_root=storage_root,
        )
        status = (
            session.query(AnalysisStatus)
            .filter_by(media_type="audio", media_id=99, step_key="stem_separation")
            .one_or_none()
        )

    assert result is None
    assert status is None


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


def test_apply_cross_project_reuse_updates_existing_pending_status_and_project_source(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"same video bytes")
    source_sha = compute_source_sha256(source, media_type="video", mode="strict")

    with _session() as session:
        session.add(Project(id=1, name="Projekt A", path=str(tmp_path / "a"), resolution="1920x1080", fps=30.0))
        session.add(Project(id=2, name="Projekt B", path=str(tmp_path / "b"), resolution="1920x1080", fps=30.0))
        session.add(ProjectSource(project_id=1, source_sha256=source_sha, current_source_path=str(source)))
        session.add(ProjectSource(project_id=2, source_sha256=source_sha, current_source_path=str(tmp_path / "old.mp4")))
        session.add(
            AnalysisJob(
                source_sha256=source_sha,
                step_id="video.plan_a.outputs",
                step_version="1",
                params_hash="plan-a",
                status="done",
                produced_by_model="PlanA",
                produced_by_model_version="v1",
                finished_at=None,
            )
        )
        session.add(
            AnalysisStatus(
                media_type="video",
                media_id=7,
                step_key="motion_scores",
                status="failed",
                error_message="old error",
            )
        )
        session.commit()

        result = apply_cross_project_reuse_status(
            session,
            source,
            media_type="video",
            media_id=7,
            current_project_id=2,
        )
        status = session.query(AnalysisStatus).filter_by(media_type="video", media_id=7, step_key="motion_scores").one()
        project_source = session.query(ProjectSource).filter_by(project_id=2, source_sha256=source_sha).one()

    assert result is not None
    assert [step.analysis_step_key for step in result.steps] == ["motion_scores", "siglip_embeddings"]
    assert result.steps[0].model == "PlanA v1"
    assert "Erzeugt am unbekannt" in result.steps[0].tooltip
    assert status.status == "done"
    assert status.error_message is None
    assert Path(project_source.current_source_path) == source


def test_lookup_cross_project_reuse_ignores_unknown_dotted_step(tmp_path: Path) -> None:
    source = tmp_path / "track.wav"
    source.write_bytes(b"same audio bytes")
    source_sha = compute_source_sha256(source, media_type="audio", mode="strict")

    with _session() as session:
        session.add(Project(id=1, name="Projekt A", path=str(tmp_path / "a"), resolution="1920x1080", fps=30.0))
        session.add(ProjectSource(project_id=1, source_sha256=source_sha, current_source_path=str(source)))
        session.add(
            AnalysisJob(
                source_sha256=source_sha,
                step_id="unknown.dotted.step",
                step_version="1",
                params_hash="unknown",
                status="done",
            )
        )
        session.commit()

        result = lookup_cross_project_reuse(session, source, media_type="audio", current_project_id=None)

    assert result is None


def test_lookup_falls_back_to_by_sha_manifest_for_per_project_db(tmp_path: Path) -> None:
    """B-539: per-project DBs hide other projects' rows. The lookup must recover
    the previous project from the global by_sha manifest instead."""
    from services.storage_provenance.source_manifest import record_manifest_job

    source = tmp_path / "track.wav"
    source.write_bytes(b"same audio bytes")
    source_sha = compute_source_sha256(source, media_type="audio", mode="strict")
    storage_root = tmp_path / "storage"
    record_manifest_job(
        storage_root,
        source_sha,
        project_id=1,
        project_name="Projekt A",
        project_path=str(tmp_path / "a"),
        step_id="audio.v2.stems",
        model="Demucs",
        finished_at=datetime(2026, 6, 14, 13, 0, 0),
    )
    _seed_artifact(storage_root, source_sha)

    with _session() as session:
        # Active (current) project DB only knows about itself — no Project A,
        # no ProjectSource, no AnalysisJob. This is the real per-project-DB case.
        session.add(Project(id=2, name="Projekt B", path=str(tmp_path / "b"), resolution="1920x1080", fps=30.0))
        session.commit()

        result = lookup_cross_project_reuse(
            session,
            source,
            media_type="audio",
            current_project_id=2,
            current_project_path=str(tmp_path / "b"),
            storage_root=storage_root,
        )

    assert result is not None
    assert result.project_name == "Projekt A"
    assert result.steps[0].analysis_step_key == "stem_separation"
    assert result.toast_message == (
        "Datei wurde bereits in Projekt Projekt A analysiert. Ergebnisse werden mitverwendet."
    )
    assert result.steps[0].tooltip == "Erzeugt am 2026-06-14 13:00 in Projekt Projekt A, Modell Demucs"


def test_manifest_fallback_ignores_current_project_only_entry(tmp_path: Path) -> None:
    """A manifest that only lists the current project must not yield a reuse hit."""
    from services.storage_provenance.source_manifest import record_manifest_job

    source = tmp_path / "track.wav"
    source.write_bytes(b"same audio bytes")
    source_sha = compute_source_sha256(source, media_type="audio", mode="strict")
    storage_root = tmp_path / "storage"
    record_manifest_job(
        storage_root,
        source_sha,
        project_id=2,
        project_name="Projekt B",
        project_path=str(tmp_path / "b"),
        step_id="audio.v2.stems",
        model="Demucs",
        finished_at=datetime(2026, 6, 14, 13, 0, 0),
    )

    with _session() as session:
        session.add(Project(id=2, name="Projekt B", path=str(tmp_path / "b"), resolution="1920x1080", fps=30.0))
        session.commit()

        result = lookup_cross_project_reuse(
            session,
            source,
            media_type="audio",
            current_project_id=2,
            current_project_path=str(tmp_path / "b"),
            storage_root=storage_root,
        )

    assert result is None


def test_apply_cross_project_reuse_status_uses_manifest_fallback(tmp_path: Path) -> None:
    """B-539 end-to-end: with only a by_sha manifest (no DB rows for the other
    project), apply_* still marks the local AnalysisStatus done."""
    from services.storage_provenance.source_manifest import record_manifest_job

    source = tmp_path / "track.wav"
    source.write_bytes(b"same audio bytes")
    source_sha = compute_source_sha256(source, media_type="audio", mode="strict")
    storage_root = tmp_path / "storage"
    record_manifest_job(
        storage_root,
        source_sha,
        project_id=1,
        project_name="Projekt A",
        project_path=str(tmp_path / "a"),
        step_id="audio.v2.stems",
        model="Demucs",
        finished_at=datetime(2026, 6, 14, 13, 0, 0),
    )
    expected_stems = _seed_stem_artifacts(storage_root, source_sha)

    with _session() as session:
        session.add(Project(id=2, name="Projekt B", path=str(tmp_path / "b"), resolution="1920x1080", fps=30.0))
        session.add(AudioTrack(id=99, project_id=2, file_path=str(source), title="Track"))
        session.commit()

        result = apply_cross_project_reuse_status(
            session,
            source,
            media_type="audio",
            media_id=99,
            current_project_id=2,
            current_project_path=str(tmp_path / "b"),
            storage_root=storage_root,
        )

        status = (
            session.query(AnalysisStatus)
            .filter_by(media_type="audio", media_id=99, step_key="stem_separation")
            .one()
        )
        track = session.get(AudioTrack, 99)

    assert result is not None
    assert status.status == "done"
    assert status.value_summary["reuse_source_project"] == "Projekt A"
    assert Path(track.stem_vocals_path) == expected_stems["vocals"]
