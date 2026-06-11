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


def test_resume_rehydrates_stem_paths_for_skipped_stemgen(tmp_path, monkeypatch, qapp):
    """OTK-018 Regression: wird stem_gen per Checkpoint uebersprungen, muss der
    Orchestrator dessen rehydrate() aufrufen, damit nachfolgende stem-geroutete
    Stages (Onset/Key/Structure) die Stem-Pfade im frischen Context vorfinden."""
    from services.audio_pipeline import stem_cache, checkpoint
    from services.audio_pipeline.orchestrator import AudioAnalysisPipeline
    from services.audio_pipeline.context import PipelineContext

    monkeypatch.setattr(stem_cache, "_STORAGE_ROOT", tmp_path)
    checkpoint.mark_stage_done(track_id=11, stage_name="stem_gen")

    class _StemGenLike:
        name = "stem_gen"
        def run(self, ctx):
            ctx.stem_paths["drums"] = "/run/drums.wav"
        def rehydrate(self, ctx):
            ctx.stem_paths["drums"] = "/cache/drums.wav"

    class _RequiresDrums:
        name = "onset"
        def __init__(self): self.ran = False
        def run(self, ctx):
            if "drums" not in ctx.stem_paths:
                raise RuntimeError("drums stem fehlt im Context (Resume-Rehydration kaputt)")
            self.ran = True

    onset = _RequiresDrums()
    pipeline = AudioAnalysisPipeline(stages=[_StemGenLike(), onset])
    ctx = PipelineContext(track_id=11, original_path="/x.wav")
    pipeline._run_stages(ctx)  # darf NICHT raisen

    assert ctx.stem_paths.get("drums") == "/cache/drums.wav"  # rehydriert, nicht run()
    assert onset.ran is True


def test_stemgen_rehydrate_db_fallback_when_no_cache(tmp_path, monkeypatch, qapp):
    """StemGenStage.rehydrate nutzt DB-stem_*_path-Fallback wenn Cache-Reuse leer."""
    from services.audio_pipeline import stages as stages_mod
    from services.audio_pipeline.context import PipelineContext

    stage = stages_mod.StemGenStage()
    monkeypatch.setattr(stage, "_try_reuse", lambda ctx: None)  # Cache-Miss

    class _Track:
        id = 7
        stem_drums_path = "/db/drums.wav"
        stem_bass_path = "/db/bass.wav"
        stem_vocals_path = None
        stem_other_path = "/db/other.wav"

    class _Sess:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def query(self, *a, **k): return self
        def filter(self, *a, **k): return self
        def first(self): return _Track()

    monkeypatch.setattr(stages_mod, "nullpool_session", lambda: _Sess())
    monkeypatch.setattr("database.AudioTrack", _Track, raising=False)

    ctx = PipelineContext(track_id=7, original_path="/x.wav")
    stage.rehydrate(ctx)
    assert ctx.stem_paths.get("drums") == "/db/drums.wav"
    assert ctx.stem_paths.get("bass") == "/db/bass.wav"
    assert ctx.stem_paths.get("other") == "/db/other.wav"
    assert "vocals" not in ctx.stem_paths  # None -> nicht gesetzt


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
