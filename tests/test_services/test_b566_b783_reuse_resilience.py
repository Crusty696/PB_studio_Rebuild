"""B-566 + B-783 — Robustheit des Cross-Project-Reuse gegen tote Kandidaten.

B-566: mehrere ``audio.v2.stems``-Eintraege im Manifest. Ein Kandidat, der
keine vollstaendigen Stems mehr aufloest (Quellprojekt geloescht), darf einen
bereits aufgeloesten Satz nicht ueberschreiben — und ``done`` darf nie ohne
gesetzte Stem-Referenzen geschrieben werden.

B-783: eine tote NTFS-Junction im by_sha-Quellordner liess ``rglob`` mitten im
Generator mit ``FileNotFoundError`` platzen und kippte damit den gesamten
Reuse-Vorgang statt nur den kaputten Kandidaten.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import AnalysisStatus, AudioTrack, Base, Project, ProjectSource
from services.storage_provenance.cross_project_reuse import (
    _source_root_has_artifacts,
    apply_cross_project_reuse_status,
)
from services.storage_provenance.layout import StorageLayout
from services.storage_provenance.source_identity import compute_source_sha256
from services.storage_provenance.source_manifest import record_manifest_job

STEMS = ("vocals", "drums", "bass", "other")


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _make_source(tmp_path: Path) -> tuple[Path, str]:
    source = tmp_path / "track.wav"
    source.write_bytes(b"same audio bytes")
    return source, compute_source_sha256(source, media_type="audio", mode="strict")


def _write_real_stems(directory: Path) -> dict[str, str]:
    directory.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, str] = {}
    for name in STEMS:
        path = directory / f"{name}.wav"
        path.write_bytes(f"{name}-stem".encode())
        artifacts[name] = str(path)
    return artifacts


def _dead_stem_artifacts(directory: Path) -> dict[str, str]:
    """Manifest-Rollen, die auf nicht mehr existierende Dateien zeigen."""
    return {name: str(directory / f"{name}.wav") for name in STEMS}


def _make_junction(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        errors="replace",
    )
    if result.returncode != 0 or not link.exists() and not _is_reparse_point(link):
        pytest.skip(f"mklink /J nicht verfuegbar: {result.stdout} {result.stderr}")


def _is_reparse_point(path: Path) -> bool:
    try:
        return path.lstat() is not None
    except OSError:
        return False


def _seed_project_rows(session: Session, tmp_path: Path, source: Path) -> None:
    session.add(
        Project(
            id=2,
            name="Projekt B",
            path=str(tmp_path / "b"),
            resolution="1920x1080",
            fps=30.0,
        )
    )
    session.add(AudioTrack(id=99, project_id=2, file_path=str(source), title="Track"))
    session.commit()


def _apply(session: Session, source: Path, tmp_path: Path, storage_root: Path):
    return apply_cross_project_reuse_status(
        session,
        source,
        media_type="audio",
        media_id=99,
        current_project_id=2,
        current_project_path=str(tmp_path / "b"),
        storage_root=storage_root,
    )


# ---------------------------------------------------------------- B-566 ----


def test_b566_healthy_stem_candidate_survives_dead_candidates(tmp_path: Path) -> None:
    """Gesunder Kandidat zuerst, danach vier tote: der gesunde Satz ueberlebt."""
    source, sha = _make_source(tmp_path)
    storage_root = tmp_path / "storage"

    healthy = _write_real_stems(tmp_path / "projekte" / "alive" / "storage" / "stems")
    record_manifest_job(
        storage_root,
        sha,
        project_id=1,
        project_name="Projekt Alive",
        project_path=str(tmp_path / "projekte" / "alive"),
        step_id="audio.v2.stems",
        model="Demucs",
        finished_at=datetime(2026, 6, 14, 13, 0, 0),
        artifacts=healthy,
    )
    # Vier Kandidaten mit aelterem finished_at -> sie werden NACH dem gesunden
    # iteriert und ueberschrieben in der Altfassung den aufgeloesten Satz.
    for idx in range(4):
        gone = tmp_path / "projekte" / f"deleted{idx}" / "storage" / "stems"
        record_manifest_job(
            storage_root,
            sha,
            project_id=10 + idx,
            project_name=f"Projekt Deleted {idx}",
            project_path=str(tmp_path / "projekte" / f"deleted{idx}"),
            step_id="audio.v2.stems",
            model="Demucs",
            finished_at=datetime(2026, 6, 10 + idx, 9, 0, 0),
            artifacts=_dead_stem_artifacts(gone),
        )

    with _session() as session:
        _seed_project_rows(session, tmp_path, source)
        result = _apply(session, source, tmp_path, storage_root)
        status = (
            session.query(AnalysisStatus)
            .filter_by(media_type="audio", media_id=99, step_key="stem_separation")
            .one_or_none()
        )
        track = session.get(AudioTrack, 99)

        assert result is not None
        assert status is not None and status.status == "done"
        for name in STEMS:
            value = getattr(track, f"stem_{name}_path")
            assert value is not None, f"stem_{name}_path fehlt trotz done"
            assert Path(value) == Path(healthy[name]).resolve()


def test_b566_dead_candidate_first_still_yields_healthy_stems(tmp_path: Path) -> None:
    """Auch umgekehrte Reihenfolge (tot zuerst) liefert den gesunden Satz."""
    source, sha = _make_source(tmp_path)
    storage_root = tmp_path / "storage"

    for idx in range(2):
        gone = tmp_path / "projekte" / f"deleted{idx}" / "storage" / "stems"
        record_manifest_job(
            storage_root,
            sha,
            project_id=10 + idx,
            project_name=f"Projekt Deleted {idx}",
            project_path=str(tmp_path / "projekte" / f"deleted{idx}"),
            step_id="audio.v2.stems",
            finished_at=datetime(2026, 6, 20 + idx, 9, 0, 0),
            artifacts=_dead_stem_artifacts(gone),
        )
    healthy = _write_real_stems(tmp_path / "projekte" / "alive" / "storage" / "stems")
    record_manifest_job(
        storage_root,
        sha,
        project_id=1,
        project_name="Projekt Alive",
        project_path=str(tmp_path / "projekte" / "alive"),
        step_id="audio.v2.stems",
        finished_at=datetime(2026, 6, 1, 9, 0, 0),
        artifacts=healthy,
    )

    with _session() as session:
        _seed_project_rows(session, tmp_path, source)
        result = _apply(session, source, tmp_path, storage_root)
        track = session.get(AudioTrack, 99)

        assert result is not None
        assert Path(track.stem_vocals_path) == Path(healthy["vocals"]).resolve()


def test_b566_no_done_without_stem_paths(tmp_path: Path) -> None:
    """Kein AnalysisStatus done, wenn kein Kandidat vier Stems aufloest."""
    source, sha = _make_source(tmp_path)
    storage_root = tmp_path / "storage"

    # by_sha haelt eine echte Datei (Guard in _manifest_hit greift), aber keinen
    # vollstaendigen Stem-Satz -> kein Kandidat ist aufloesbar.
    partial = StorageLayout(storage_root).source_root(sha) / "audio" / "stems"
    partial.mkdir(parents=True, exist_ok=True)
    (partial / "drums.wav").write_bytes(b"only-drums")

    for idx in range(3):
        gone = tmp_path / "projekte" / f"deleted{idx}" / "storage" / "stems"
        record_manifest_job(
            storage_root,
            sha,
            project_id=10 + idx,
            project_name=f"Projekt Deleted {idx}",
            project_path=str(tmp_path / "projekte" / f"deleted{idx}"),
            step_id="audio.v2.stems",
            finished_at=datetime(2026, 6, 10 + idx, 9, 0, 0),
            artifacts=_dead_stem_artifacts(gone),
        )

    with _session() as session:
        _seed_project_rows(session, tmp_path, source)
        result = _apply(session, source, tmp_path, storage_root)
        status = (
            session.query(AnalysisStatus)
            .filter_by(media_type="audio", media_id=99, step_key="stem_separation")
            .one_or_none()
        )
        track = session.get(AudioTrack, 99)

        assert result is None
        assert status is None
        assert track.stem_vocals_path is None


# ---------------------------------------------------------------- B-783 ----


def test_b783_dead_junction_does_not_crash_artifact_scan(tmp_path: Path) -> None:
    source, sha = _make_source(tmp_path)
    storage_root = tmp_path / "storage"
    root = StorageLayout(storage_root).ensure_source_root(sha)
    (root / "audio" / "real.wav").write_bytes(b"artifact")
    _make_junction(root / "audio" / "stems", tmp_path / "nie_existiert")

    assert _source_root_has_artifacts(storage_root, sha) is True


def test_b783_dead_junction_only_means_no_artifacts(tmp_path: Path) -> None:
    source, sha = _make_source(tmp_path)
    storage_root = tmp_path / "storage"
    root = StorageLayout(storage_root).ensure_source_root(sha)
    _make_junction(root / "audio" / "stems", tmp_path / "nie_existiert")

    assert _source_root_has_artifacts(storage_root, sha) is False


def test_b783_healthy_junction_still_counts_as_artifact(tmp_path: Path) -> None:
    """Bestandsverhalten: eine lebende Junction liefert weiterhin Artefakte."""
    source, sha = _make_source(tmp_path)
    storage_root = tmp_path / "storage"
    root = StorageLayout(storage_root).ensure_source_root(sha)
    real = tmp_path / "echte_stems"
    _write_real_stems(real)
    _make_junction(root / "audio" / "stems", real)

    assert _source_root_has_artifacts(storage_root, sha) is True


def test_b783_dead_junction_does_not_kill_whole_reuse(tmp_path: Path) -> None:
    """Ein toter Kandidat darf den gesunden nicht mitreissen (End-to-End)."""
    source, sha = _make_source(tmp_path)
    storage_root = tmp_path / "storage"
    root = StorageLayout(storage_root).ensure_source_root(sha)
    _make_junction(root / "audio" / "stems", tmp_path / "geloeschtes_projekt")

    healthy = _write_real_stems(tmp_path / "projekte" / "alive" / "storage" / "stems")
    record_manifest_job(
        storage_root,
        sha,
        project_id=1,
        project_name="Projekt Alive",
        project_path=str(tmp_path / "projekte" / "alive"),
        step_id="audio.v2.stems",
        model="Demucs",
        finished_at=datetime(2026, 6, 14, 13, 0, 0),
        artifacts=healthy,
    )

    with _session() as session:
        _seed_project_rows(session, tmp_path, source)
        result = _apply(session, source, tmp_path, storage_root)
        status = (
            session.query(AnalysisStatus)
            .filter_by(media_type="audio", media_id=99, step_key="stem_separation")
            .one_or_none()
        )
        track = session.get(AudioTrack, 99)
        project_source = (
            session.query(ProjectSource)
            .filter_by(project_id=2, source_sha256=sha)
            .one_or_none()
        )

        assert result is not None, "toter Kandidat hat den gesamten Reuse gekippt"
        assert status is not None and status.status == "done"
        assert project_source is not None
        assert Path(track.stem_vocals_path) == Path(healthy["vocals"]).resolve()
