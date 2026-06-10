"""Plan: AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17

T1.2: AudioAnalysisPipeline - Orchestrator (QObject, strict-sequential).
"""
from __future__ import annotations

from unittest.mock import MagicMock
import threading
import time
import pytest


class _RecordingStage:
    """Mock-Stage zum Aufzeichnen der Ausfuehrungsreihenfolge."""
    name = "_recording"

    def __init__(self, name, order_log, fail=False, sleep_ms=0):
        self.name = name
        self._order_log = order_log
        self._fail = fail
        self._sleep_ms = sleep_ms
        self.run_count = 0

    def run(self, context):
        self._order_log.append(self.name)
        self.run_count += 1
        if self._sleep_ms:
            time.sleep(self._sleep_ms / 1000.0)
        if self._fail:
            raise RuntimeError(f"{self.name} failed (test)")
        context.set_result(self.name, {"ok": True})


@pytest.fixture
def qapp(qtbot=None):
    """QApplication fuer Signal-Tests (PySide6)."""
    from PySide6.QtWidgets import QApplication
    import sys
    app = QApplication.instance() or QApplication(sys.argv)
    return app


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """Isoliere Checkpoint-Storage pro Test (T4.2)."""
    from services.audio_pipeline import stem_cache
    monkeypatch.setattr(stem_cache, "_STORAGE_ROOT", tmp_path)
    yield tmp_path


def test_pipeline_class_exists():
    from services.audio_pipeline.orchestrator import AudioAnalysisPipeline
    assert AudioAnalysisPipeline is not None


def test_pipeline_is_qobject():
    from PySide6.QtCore import QObject
    from services.audio_pipeline.orchestrator import AudioAnalysisPipeline
    assert issubclass(AudioAnalysisPipeline, QObject)


def test_pipeline_runs_stages_in_strict_order(qapp):
    """Strict-Sequential: Stages laufen exakt in Reihenfolge."""
    from services.audio_pipeline.orchestrator import AudioAnalysisPipeline
    from services.audio_pipeline.context import PipelineContext

    order = []
    stages = [
        _RecordingStage("stem_gen", order),
        _RecordingStage("beat_grid", order),
        _RecordingStage("onset", order),
    ]
    pipeline = AudioAnalysisPipeline(stages=stages)
    ctx = PipelineContext(track_id=1, original_path="/x.wav")
    pipeline._run_stages(ctx)  # Synchron-Variante fuer Test
    assert order == ["stem_gen", "beat_grid", "onset"]


def test_pipeline_fail_fast_on_stem_gen_failure(qapp):
    """A-1 / AC-9: Demucs-Fail (=StemGen) -> Pipeline-Stop, nachfolgende Stages laufen NICHT."""
    from services.audio_pipeline.orchestrator import AudioAnalysisPipeline
    from services.audio_pipeline.context import PipelineContext

    order = []
    stages = [
        _RecordingStage("stem_gen", order, fail=True),
        _RecordingStage("beat_grid", order),
        _RecordingStage("onset", order),
    ]
    pipeline = AudioAnalysisPipeline(stages=stages)
    ctx = PipelineContext(track_id=1, original_path="/x.wav")
    with pytest.raises(RuntimeError):
        pipeline._run_stages(ctx)
    assert order == ["stem_gen"]


def test_pipeline_emits_signals_per_stage(qapp):
    """Signals: stage_started, stage_done, pipeline_done."""
    from services.audio_pipeline.orchestrator import AudioAnalysisPipeline
    from services.audio_pipeline.context import PipelineContext

    started_evts = []
    done_evts = []
    pipeline_done_evts = []
    stages = [_RecordingStage("a", []), _RecordingStage("b", [])]
    pipeline = AudioAnalysisPipeline(stages=stages)
    pipeline.stage_started.connect(lambda name: started_evts.append(name))
    pipeline.stage_done.connect(lambda name, payload: done_evts.append(name))
    pipeline.pipeline_done.connect(lambda tid: pipeline_done_evts.append(tid))

    ctx = PipelineContext(track_id=42, original_path="/x.wav")
    pipeline._run_stages(ctx)

    assert started_evts == ["a", "b"]
    assert done_evts == ["a", "b"]
    assert pipeline_done_evts == [42]


def test_pipeline_emits_stage_failed_on_exception(qapp):
    """AC-9: stage_failed Signal mit Exception."""
    from services.audio_pipeline.orchestrator import AudioAnalysisPipeline
    from services.audio_pipeline.context import PipelineContext

    failed_evts = []
    stages = [_RecordingStage("x", [], fail=True)]
    pipeline = AudioAnalysisPipeline(stages=stages)
    pipeline.stage_failed.connect(lambda name, msg: failed_evts.append((name, msg)))

    ctx = PipelineContext(track_id=1, original_path="/x.wav")
    with pytest.raises(RuntimeError):
        pipeline._run_stages(ctx)
    assert len(failed_evts) == 1
    assert failed_evts[0][0] == "x"
    assert "failed" in failed_evts[0][1]


def test_pipeline_run_is_non_blocking(qapp):
    """A-3 / fixt R-11: pipeline.run() returnt sofort, Stages laufen auf QThreadPool."""
    from services.audio_pipeline.orchestrator import AudioAnalysisPipeline
    from services.audio_pipeline.context import PipelineContext

    stages = [_RecordingStage("slow", [], sleep_ms=200)]
    pipeline = AudioAnalysisPipeline(stages=stages)
    ctx = PipelineContext(track_id=1, original_path="/x.wav")

    t0 = time.time()
    pipeline.run(ctx)
    elapsed_ms = (time.time() - t0) * 1000

    # run() darf nicht 200ms blockieren - Runnable laeuft async
    assert elapsed_ms < 100, f"run() blockierte {elapsed_ms:.0f}ms (sollte <100ms sein)"


def test_pipeline_has_required_signals(qapp):
    from PySide6.QtCore import Signal
    from services.audio_pipeline.orchestrator import AudioAnalysisPipeline

    pipeline = AudioAnalysisPipeline(stages=[])
    # Signals existieren als Attribute (bound zur Instanz)
    assert hasattr(pipeline, "stage_started")
    assert hasattr(pipeline, "stage_done")
    assert hasattr(pipeline, "stage_failed")
    assert hasattr(pipeline, "pipeline_done")
