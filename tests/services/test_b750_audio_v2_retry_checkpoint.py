"""B-750: gezielter V2-Retry setzt nur angeforderte Stage zurück."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


def test_checkpoint_reset_stages_removes_only_requested(tmp_path, monkeypatch):
    from services.audio_pipeline import checkpoint, stem_cache

    monkeypatch.setattr(stem_cache, "_STORAGE_ROOT", tmp_path)
    for name in ("stem_gen", "onset", "av_pacing"):
        checkpoint.mark_stage_done(7, name)

    checkpoint.reset_stages(7, ("onset",))

    assert checkpoint.stages_done(7) == ["stem_gen", "av_pacing"]


@pytest.mark.parametrize(
    ("step_key", "expected_run", "expected_rehydrate"),
    [
        ("onset_detection", ["onset"], ["stem_gen"]),
        ("av_pacing_curves", ["av_pacing"], []),
    ],
)
def test_targeted_worker_runs_only_requested_stage_and_prerequisite(
    monkeypatch, qapp, step_key, expected_run, expected_rehydrate
):
    from services.audio_pipeline import checkpoint, stages as stages_module
    import services.analysis_status_service as status_module
    from workers.audio_pipeline_v2_worker import AudioPipelineV2Worker

    ran: list[str] = []
    rehydrated: list[str] = []
    reset: list[tuple[int, tuple[str, ...]]] = []

    class _Stage:
        def __init__(self, name):
            self.name = name

        def rehydrate(self, _context):
            rehydrated.append(self.name)

        def run(self, context):
            ran.append(self.name)
            context.set_result(self.name, {"ok": True})

    fake_stages = [_Stage("stem_gen"), _Stage("onset"), _Stage("av_pacing")]
    monkeypatch.setattr(stages_module, "build_default_stages", lambda: fake_stages)
    monkeypatch.setattr(checkpoint, "invalidate_if_stale", lambda *_args: False)
    monkeypatch.setattr(
        checkpoint,
        "reset_stages",
        lambda track_id, names: reset.append((track_id, tuple(names))),
        raising=False,
    )
    monkeypatch.setattr(
        checkpoint,
        "is_stage_done",
        lambda _track_id, name: name == "stem_gen" and step_key == "onset_detection",
    )
    monkeypatch.setattr(checkpoint, "mark_stage_done", lambda *_args: None)
    monkeypatch.setattr(status_module, "mark_started", lambda *_args: None)
    monkeypatch.setattr(status_module, "mark_done", lambda *_args: None)

    worker = AudioPipelineV2Worker(
        audio_track_id=7,
        file_path="C:/isolated/audio.wav",
        retry_step_keys=(step_key,),
    )
    finished = []
    worker.finished.connect(lambda track_id, results: finished.append((track_id, results)))
    worker.run()

    assert reset == [(7, tuple(expected_run))]
    assert ran == expected_run
    assert rehydrated == expected_rehydrate
    assert finished and finished[0][0] == 7
