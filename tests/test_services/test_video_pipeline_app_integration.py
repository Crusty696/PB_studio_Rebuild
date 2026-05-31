"""Tests fuer den App-Integration-Entry-Point der Video-Pipeline-Engine.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19. Feature-Flag-Verhalten (deterministisch,
kein GPU). Der Live-Pipeline-Lauf liegt in test_video_pipeline_e2e_live.py.
"""
from __future__ import annotations

from services.video_pipeline.app_integration import engine_enabled, FEATURE_FLAG


def test_engine_disabled_by_default(monkeypatch):
    monkeypatch.delenv(FEATURE_FLAG, raising=False)
    assert engine_enabled() is False


def test_engine_enabled_when_flag_is_1(monkeypatch):
    monkeypatch.setenv(FEATURE_FLAG, "1")
    assert engine_enabled() is True


def test_engine_disabled_for_other_values(monkeypatch):
    monkeypatch.setenv(FEATURE_FLAG, "0")
    assert engine_enabled() is False
    monkeypatch.setenv(FEATURE_FLAG, "true")
    assert engine_enabled() is False


def test_build_pipeline_assembles_seven_stages(monkeypatch, tmp_path):
    """build_pipeline baut die Kette ohne GPU/Modelle zu laden (lazy load)."""
    # Dummy-Quelldatei (stream_sha256 liest sie, kein Decode noetig)
    src = tmp_path / "x.mp4"
    src.write_bytes(b"\x00\x01\x02\x03")
    from services.video_pipeline.app_integration import build_pipeline
    pipe, (siglip, raft) = build_pipeline(
        track_id=1, source_path=src, storage_dir=tmp_path / "store",
    )
    assert len(pipe.stages) == 7
    # Modelle noch nicht geladen (lazy)
    assert raft.is_loaded is False


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
