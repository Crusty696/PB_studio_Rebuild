"""Plan: AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17

T4.2: Orchestrator Resume-Logik (skip completed stages, mark stage done).
"""
from __future__ import annotations

from unittest.mock import patch
import pytest


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    import sys
    return QApplication.instance() or QApplication(sys.argv)


class _RecordingStage:
    def __init__(self, name, order):
        self.name = name
        self._order = order
    def run(self, ctx):
        self._order.append(self.name)
        ctx.set_result(self.name, {"ok": True})


def test_resume_skips_completed_stages(tmp_path, monkeypatch, qapp):
    from services.audio_pipeline import stem_cache, checkpoint
    from services.audio_pipeline.orchestrator import AudioAnalysisPipeline
    from services.audio_pipeline.context import PipelineContext

    monkeypatch.setattr(stem_cache, "_STORAGE_ROOT", tmp_path)
    # Markiere "stem_gen" als done
    checkpoint.mark_stage_done(track_id=1, stage_name="stem_gen")

    order = []
    pipeline = AudioAnalysisPipeline(stages=[
        _RecordingStage("stem_gen", order),
        _RecordingStage("beat_grid", order),
        _RecordingStage("onset", order),
    ])
    ctx = PipelineContext(track_id=1, original_path="/x.wav")
    pipeline._run_stages(ctx)

    # stem_gen wurde uebersprungen
    assert "stem_gen" not in order
    assert "beat_grid" in order
    assert "onset" in order


def test_resume_runs_remaining_stages(tmp_path, monkeypatch, qapp):
    from services.audio_pipeline import stem_cache, checkpoint
    from services.audio_pipeline.orchestrator import AudioAnalysisPipeline
    from services.audio_pipeline.context import PipelineContext

    monkeypatch.setattr(stem_cache, "_STORAGE_ROOT", tmp_path)
    for sn in ("stem_gen", "beat_grid"):
        checkpoint.mark_stage_done(track_id=2, stage_name=sn)

    order = []
    pipeline = AudioAnalysisPipeline(stages=[
        _RecordingStage("stem_gen", order),
        _RecordingStage("beat_grid", order),
        _RecordingStage("onset", order),
        _RecordingStage("key", order),
    ])
    ctx = PipelineContext(track_id=2, original_path="/x.wav")
    pipeline._run_stages(ctx)

    assert order == ["onset", "key"]


def test_run_marks_stage_done_after_success(tmp_path, monkeypatch, qapp):
    """Orchestrator markiert nach Stage-Success automatisch checkpoint.mark_stage_done."""
    from services.audio_pipeline import stem_cache, checkpoint
    from services.audio_pipeline.orchestrator import AudioAnalysisPipeline
    from services.audio_pipeline.context import PipelineContext

    monkeypatch.setattr(stem_cache, "_STORAGE_ROOT", tmp_path)

    pipeline = AudioAnalysisPipeline(stages=[_RecordingStage("lufs", [])])
    ctx = PipelineContext(track_id=3, original_path="/x.wav")
    pipeline._run_stages(ctx)

    assert checkpoint.is_stage_done(3, "lufs") is True


def test_run_does_not_mark_stage_done_on_failure(tmp_path, monkeypatch, qapp):
    from services.audio_pipeline import stem_cache, checkpoint
    from services.audio_pipeline.orchestrator import AudioAnalysisPipeline
    from services.audio_pipeline.context import PipelineContext

    monkeypatch.setattr(stem_cache, "_STORAGE_ROOT", tmp_path)

    class _FailStage:
        name = "boom"
        def run(self, ctx):
            raise RuntimeError("boom")

    pipeline = AudioAnalysisPipeline(stages=[_FailStage()])
    ctx = PipelineContext(track_id=4, original_path="/x.wav")
    with pytest.raises(RuntimeError):
        pipeline._run_stages(ctx)
    assert checkpoint.is_stage_done(4, "boom") is False
