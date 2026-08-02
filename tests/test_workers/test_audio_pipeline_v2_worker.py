"""OTK-018: AudioPipelineV2Worker faehrt den Orchestrator + emittiert Signale."""
from __future__ import annotations

import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    import sys
    return QApplication.instance() or QApplication(sys.argv)


class _FakeStage:
    def __init__(self, name):
        self.name = name
    def run(self, ctx):
        ctx.set_result(self.name, {"ok": True})


def test_worker_runs_pipeline_and_emits_finished(qapp, tmp_path, monkeypatch):
    from services.audio_pipeline import stages as stages_mod, stem_cache, checkpoint
    monkeypatch.setattr(stem_cache, "_STORAGE_ROOT", tmp_path)
    monkeypatch.setattr(checkpoint, "_STATE_ROOT", tmp_path, raising=False)
    monkeypatch.setattr(stages_mod, "build_default_stages",
                        lambda: [_FakeStage("stem_gen"), _FakeStage("beat_grid")])

    from workers.audio_pipeline_v2_worker import AudioPipelineV2Worker
    worker = AudioPipelineV2Worker(audio_track_id=99, file_path="/x.wav")

    got = {}
    progress = []
    worker.finished.connect(lambda tid, res: got.update({"tid": tid, "res": res}))
    worker.error.connect(lambda tid, err: got.update({"err": err}))
    worker.progress.connect(lambda pct, msg: progress.append((pct, msg)))

    worker.run()

    assert "err" not in got
    assert got["tid"] == 99
    assert set(got["res"].keys()) == {"stem_gen", "beat_grid"}
    assert progress and progress[-1][0] == 100


def test_worker_emits_error_on_stage_failure(qapp, tmp_path, monkeypatch):
    from services.audio_pipeline import stages as stages_mod, stem_cache, checkpoint
    monkeypatch.setattr(stem_cache, "_STORAGE_ROOT", tmp_path)
    monkeypatch.setattr(checkpoint, "_STATE_ROOT", tmp_path, raising=False)

    class _Boom:
        name = "stem_gen"
        def run(self, ctx):
            raise RuntimeError("demucs kaputt")

    monkeypatch.setattr(stages_mod, "build_default_stages", lambda: [_Boom()])

    from workers.audio_pipeline_v2_worker import AudioPipelineV2Worker
    worker = AudioPipelineV2Worker(audio_track_id=5, file_path="/x.wav")
    got = {}
    worker.finished.connect(lambda tid, res: got.update({"fin": True}))
    worker.error.connect(lambda tid, err: got.update({"tid": tid, "err": err}))
    worker.run()

    assert "fin" not in got
    assert got["tid"] == 5
    assert "demucs kaputt" in got["err"]


def test_worker_marks_user_cancel_as_cancelled_not_error(qapp, tmp_path, monkeypatch):
    from services.audio_pipeline import stages as stages_mod, stem_cache, checkpoint
    import services.analysis_status_service as status_service

    monkeypatch.setattr(stem_cache, "_STORAGE_ROOT", tmp_path)
    monkeypatch.setattr(checkpoint, "_STATE_ROOT", tmp_path, raising=False)

    class _CancelledStage:
        name = "av_pacing"

        def run(self, _ctx):
            raise RuntimeError("AV-Pacing abgebrochen (User-Cancel)")

    monkeypatch.setattr(stages_mod, "build_default_stages", lambda: [_CancelledStage()])
    cancelled = []
    errors = []
    monkeypatch.setattr(status_service, "mark_started", lambda *args: None)
    monkeypatch.setattr(status_service, "mark_cancelled", lambda *args: cancelled.append(args))
    monkeypatch.setattr(status_service, "mark_error", lambda *args: errors.append(args))

    from workers.audio_pipeline_v2_worker import AudioPipelineV2Worker

    worker = AudioPipelineV2Worker(audio_track_id=8, file_path="/x.wav")
    emitted = []
    worker.error.connect(lambda tid, err: emitted.append((tid, err)))
    worker.run()

    assert cancelled == [("audio", 8, "av_pacing_curves")]
    assert errors == []
    assert emitted == [(8, "AV-Pacing abgebrochen (User-Cancel)")]


def test_worker_cancellation(qapp, tmp_path, monkeypatch):
    from services.audio_pipeline import checkpoint, stages as stages_mod, stem_cache

    monkeypatch.setattr(stem_cache, "_STORAGE_ROOT", tmp_path)
    monkeypatch.setattr(checkpoint, "_STATE_ROOT", tmp_path, raising=False)

    class _CancellableStage:
        name = "stem_gen"

        def run(self, ctx):
            if ctx.should_stop and ctx.should_stop():
                raise RuntimeError("Audio-V2 Pipeline abgebrochen (User-Cancel)")
            ctx.set_result(self.name, {"ok": True})

    monkeypatch.setattr(stages_mod, "build_default_stages", lambda: [_CancellableStage()])

    from workers.audio_pipeline_v2_worker import AudioPipelineV2Worker

    worker = AudioPipelineV2Worker(audio_track_id=7, file_path="/x.wav")
    worker.cancel()

    got = {}
    worker.finished.connect(lambda tid, res: got.update({"fin": True}))
    worker.error.connect(lambda tid, err: got.update({"tid": tid, "err": err}))

    worker.run()

    assert "fin" not in got
    assert "err" not in got
