"""Ein Proxy allein ist kein Beleg fuer Motion-Daten oder SigLIP-Embeddings.

Befund (Audit 2026-07-27, Bereich db-persistenz, bestaetigt + live reproduziert):
``_manifest_artifacts_exist`` prueft mit ``any(...)``. Ein Manifest-Job
``video.plan_a.outputs``, der nur ``artifacts={"proxy": ...}`` traegt (Projekt A
hat fuer das Video nur einen Proxy erzeugt), liess ``_video_outputs_reachable``
True liefern -> beide Schritte ``motion_scores`` und ``siglip_embeddings`` wurden
in Projekt B als ``done`` geschrieben, obwohl dort weder Motion-Daten noch
VectorDB-Embeddings existieren (die VectorDB ist projektlokal).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import AnalysisStatus, Base, Project
from services.storage_provenance.cross_project_reuse import (
    _video_outputs_reachable,
    apply_cross_project_reuse_status,
)
from services.storage_provenance.source_identity import compute_source_sha256
from services.storage_provenance.source_manifest import record_manifest_job


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_video_outputs_not_reachable_with_proxy_only_manifest(tmp_path: Path) -> None:
    proxy = tmp_path / "proxy.mp4"
    proxy.write_bytes(b"proxy-bytes")
    storage_root = tmp_path / "storage"

    assert (
        _video_outputs_reachable(storage_root, "0" * 64, {"proxy": str(proxy)})
        is False
    )


def test_video_outputs_reachable_with_real_motion_artifact(tmp_path: Path) -> None:
    """Gegenprobe: echte Analyse-Artefakte zaehlen weiterhin."""
    motion = tmp_path / "motion.json"
    motion.write_text("{}", encoding="utf-8")
    storage_root = tmp_path / "storage"

    assert (
        _video_outputs_reachable(storage_root, "0" * 64, {"motion": str(motion)})
        is True
    )


def test_proxy_only_manifest_does_not_mark_video_steps_done(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"same video bytes")
    source_sha = compute_source_sha256(source, media_type="video", mode="strict")
    storage_root = tmp_path / "storage"

    proxy = tmp_path / "projA" / "proxy.mp4"
    proxy.parent.mkdir(parents=True)
    proxy.write_bytes(b"proxy-bytes")

    record_manifest_job(
        storage_root,
        source_sha,
        project_id=1,
        project_name="Projekt A",
        project_path=str(tmp_path / "a"),
        step_id="video.plan_a.outputs",
        model="PlanA",
        finished_at=datetime(2026, 7, 20, 10, 0, 0),
        artifacts={"proxy": str(proxy)},
    )

    with _session() as session:
        session.add(
            Project(id=2, name="Projekt B", path=str(tmp_path / "b"),
                    resolution="1920x1080", fps=30.0)
        )
        session.commit()

        result = apply_cross_project_reuse_status(
            session,
            source,
            media_type="video",
            media_id=7,
            current_project_id=2,
            current_project_path=str(tmp_path / "b"),
            storage_root=storage_root,
        )
        rows = (
            session.query(AnalysisStatus)
            .filter_by(media_type="video", media_id=7)
            .all()
        )

    assert result is None
    assert rows == []
