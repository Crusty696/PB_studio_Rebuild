"""B-543..B-546: robustness of the by_sha provenance manifest + reuse lookup."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import Base, Project
from services.storage_provenance.cross_project_reuse import lookup_cross_project_reuse
from services.storage_provenance.source_identity import compute_source_sha256
from services.storage_provenance.source_manifest import (
    MANIFEST_NAME,
    manifest_path,
    read_manifest_jobs,
    record_manifest_job,
)
from services.storage_provenance.layout import StorageLayout


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_artifact(storage_root, source_sha) -> None:
    art = StorageLayout(storage_root).source_root(source_sha) / "audio" / "stems" / "drums.wav"
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_bytes(b"stem-bytes")


def _sha(tmp_path: Path) -> tuple[Path, str]:
    src = tmp_path / "track.wav"
    src.write_bytes(b"same audio bytes")
    return src, compute_source_sha256(src, media_type="audio", mode="strict")


def test_b544_no_reuse_when_artifacts_missing(tmp_path: Path) -> None:
    src, sha = _sha(tmp_path)
    sr = tmp_path / "storage"
    record_manifest_job(sr, sha, project_id=1, project_name="A", project_path=str(tmp_path / "a"),
                        step_id="audio.v2.stems", model="Demucs", finished_at=datetime(2026, 6, 14, 13, 0))
    # NO artifact seeded
    with _session() as s:
        s.add(Project(id=2, name="B", path=str(tmp_path / "b"), resolution="1920x1080", fps=30.0))
        s.commit()
        result = lookup_cross_project_reuse(s, src, media_type="audio", current_project_id=2,
                                            current_project_path=str(tmp_path / "b"), storage_root=sr)
    assert result is None


def test_b544_reuse_when_artifacts_present(tmp_path: Path) -> None:
    src, sha = _sha(tmp_path)
    sr = tmp_path / "storage"
    record_manifest_job(sr, sha, project_id=1, project_name="A", project_path=str(tmp_path / "a"),
                        step_id="audio.v2.stems", model="Demucs", finished_at=datetime(2026, 6, 14, 13, 0))
    _seed_artifact(sr, sha)
    with _session() as s:
        s.add(Project(id=2, name="B", path=str(tmp_path / "b"), resolution="1920x1080", fps=30.0))
        s.commit()
        result = lookup_cross_project_reuse(s, src, media_type="audio", current_project_id=2,
                                            current_project_path=str(tmp_path / "b"), storage_root=sr)
    assert result is not None
    assert result.project_name == "A"


def test_b546_dedup_normalizes_path_case(tmp_path: Path) -> None:
    src, sha = _sha(tmp_path)
    sr = tmp_path / "storage"
    base = tmp_path / "Proj"
    record_manifest_job(sr, sha, project_id=1, project_name="P", project_path=str(base),
                        step_id="audio.v2.stems")
    record_manifest_job(sr, sha, project_id=1, project_name="P", project_path=str(base).upper() + "\\.",
                        step_id="audio.v2.stems")
    assert len(read_manifest_jobs(sr, sha)) == 1


def test_b546_hit_picks_most_recent(tmp_path: Path) -> None:
    src, sha = _sha(tmp_path)
    sr = tmp_path / "storage"
    record_manifest_job(sr, sha, project_id=1, project_name="Older", project_path=str(tmp_path / "old"),
                        step_id="audio.v2.stems", model="Demucs", finished_at=datetime(2026, 6, 10, 9, 0))
    record_manifest_job(sr, sha, project_id=1, project_name="Newer", project_path=str(tmp_path / "new"),
                        step_id="audio.v2.stems", model="Demucs", finished_at=datetime(2026, 6, 14, 13, 0))
    _seed_artifact(sr, sha)
    with _session() as s:
        s.add(Project(id=2, name="Cur", path=str(tmp_path / "cur"), resolution="1920x1080", fps=30.0))
        s.commit()
        result = lookup_cross_project_reuse(s, src, media_type="audio", current_project_id=2,
                                            current_project_path=str(tmp_path / "cur"), storage_root=sr)
    assert result is not None
    assert result.project_name == "Newer"


def test_b543_corrupt_manifest_backed_up_not_wiped(tmp_path: Path) -> None:
    src, sha = _sha(tmp_path)
    sr = tmp_path / "storage"
    record_manifest_job(sr, sha, project_id=1, project_name="P", project_path=str(tmp_path / "a"),
                        step_id="audio.v2.stems")
    mpath = manifest_path(sr, sha)
    mpath.write_text("{ this is not valid json", encoding="utf-8")
    record_manifest_job(sr, sha, project_id=1, project_name="P", project_path=str(tmp_path / "a"),
                        step_id="audio.v2.stems")
    assert list(mpath.parent.glob(MANIFEST_NAME + "*.corrupt")), "corrupt manifest should be backed up"
    assert len(read_manifest_jobs(sr, sha)) == 1
    assert not list(mpath.parent.glob(MANIFEST_NAME + ".tmp*")), "no temp leftovers (atomic write)"


def test_b543_concurrent_writes_no_lost_update(tmp_path: Path) -> None:
    """Two threads writing different projects for the same source: both entries
    survive (file lock + atomic write prevent lost updates)."""
    import threading

    src, sha = _sha(tmp_path)
    sr = tmp_path / "storage"

    def writer(name: str) -> None:
        record_manifest_job(sr, sha, project_id=1, project_name=name,
                            project_path=str(tmp_path / name), step_id="audio.v2.stems",
                            model="Demucs", finished_at=datetime(2026, 6, 14, 13, 0))

    threads = [threading.Thread(target=writer, args=(f"P{i}",)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    jobs = read_manifest_jobs(sr, sha)
    names = {j.get("project_name") for j in jobs}
    assert names == {f"P{i}" for i in range(8)}, f"lost update: got {names}"


def test_b548_merge_keeps_richer_entry(tmp_path: Path) -> None:
    """B-548: a poorer writer (model/finished_at=None, e.g. open_project migration)
    must not overwrite a richer record_done entry for the same (path, step)."""
    src, sha = _sha(tmp_path)
    sr = tmp_path / "storage"
    base = tmp_path / "Proj"
    record_manifest_job(sr, sha, project_id=1, project_name="P", project_path=str(base),
                        step_id="audio.v2.stems", model="Demucs", model_version="htdemucs_ft",
                        finished_at=datetime(2026, 6, 14, 13, 0))
    # migration-style poorer write (no model / finished_at)
    record_manifest_job(sr, sha, project_id=1, project_name="P", project_path=str(base),
                        step_id="audio.v2.stems")
    jobs = read_manifest_jobs(sr, sha)
    assert len(jobs) == 1
    assert jobs[0]["model"] == "Demucs"
    assert jobs[0]["model_version"] == "htdemucs_ft"
    assert jobs[0]["finished_at"] is not None
