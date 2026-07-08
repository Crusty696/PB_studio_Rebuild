"""Tests fuer den App-Integration-Entry-Point der Video-Pipeline-Engine.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19. Feature-Flag-Verhalten (deterministisch,
kein GPU). Der Live-Pipeline-Lauf liegt in test_video_pipeline_e2e_live.py.
"""
from __future__ import annotations

from services.video_pipeline.app_integration import engine_enabled, FEATURE_FLAG


def test_engine_disabled_by_default(monkeypatch):
    # M3 (D-065): kein Setting-Store im Test -> Fallback greift auf False.
    monkeypatch.delenv(FEATURE_FLAG, raising=False)
    assert engine_enabled() is False


def test_engine_enabled_when_flag_is_1(monkeypatch):
    monkeypatch.setenv(FEATURE_FLAG, "1")
    assert engine_enabled() is True


def test_engine_disabled_for_zero(monkeypatch):
    """0 als Env-Override erzwingt AUS (Test-Determinismus)."""
    monkeypatch.setenv(FEATURE_FLAG, "0")
    assert engine_enabled() is False


def test_engine_env_truthy_values_enable(monkeypatch):
    """M3 (D-065): Env-Override akzeptiert jetzt dieselbe Truthy-Menge wie
    das T1.1-Studio-Brain-Gate (1/true/yes/on) — vorher nur exakt '1'."""
    for val in ("true", "yes", "on", "TRUE"):
        monkeypatch.setenv(FEATURE_FLAG, val)
        assert engine_enabled() is True


def test_build_pipeline_assembles_eight_stages(monkeypatch, tmp_path):
    """build_pipeline baut die Kette ohne GPU/Modelle zu laden (lazy load).

    NEUBAU-VOLLINTEGRATION M3 (D-065): DbPersistStage kam als 8. Stage
    (Scene + VectorDB-Write) hinzu — sie muss ZULETZT laufen."""
    # Dummy-Quelldatei (stream_sha256 liest sie, kein Decode noetig)
    src = tmp_path / "x.mp4"
    src.write_bytes(b"\x00\x01\x02\x03")
    from services.video_pipeline.app_integration import build_pipeline
    pipe, (siglip, raft) = build_pipeline(
        track_id=1, source_path=src, storage_dir=tmp_path / "store",
    )
    assert len(pipe.stages) == 8
    assert pipe.stages[-1].stage_id == "db_persist"
    # Modelle noch nicht geladen (lazy)
    assert raft.is_loaded is False


def test_b574_build_pipeline_loads_existing_checkpoint(tmp_path):
    from services.video_pipeline.app_integration import build_pipeline
    from services.video_pipeline.primitives.resume_checkpoint import ResumeCheckpoint
    from services.video_pipeline.primitives.stream_hasher import stream_sha256

    src = tmp_path / "x.mp4"
    src.write_bytes(b"\x00\x01\x02\x03")
    storage = tmp_path / "store"
    storage.mkdir()
    source_sha = stream_sha256(src)
    checkpoint = ResumeCheckpoint(
        storage / "checkpoint.json",
        track_id=1,
        stream_sha256=source_sha,
    )
    checkpoint.update_stage("proxy_gen", status="done")
    checkpoint.save()

    pipe, _services = build_pipeline(
        track_id=1,
        source_path=src,
        storage_dir=storage,
    )

    assert pipe.checkpoint.completed_stages() == ["proxy_gen"]


def test_engine_worker_has_dispatcher_contract_signals():
    """worker_dispatcher._start_worker_thread verbindet worker.error / finished /
    progress. Fehlt eines -> AttributeError beim Dispatch (Worker startet nie).

    Regression fuer den live (pb-gui-tester 2026-05-31) gefundenen Crash:
    VideoPipelineEngineWorker hatte kein error-Signal.
    """
    from workers.video import VideoPipelineEngineWorker
    w = VideoPipelineEngineWorker([])
    for sig in ("error", "finished", "progress", "item_done", "item_error"):
        assert hasattr(w, sig), f"VideoPipelineEngineWorker fehlt Signal '{sig}'"
