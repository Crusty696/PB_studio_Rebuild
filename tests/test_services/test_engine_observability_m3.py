"""NEUBAU-VOLLINTEGRATION M3 (DEAD-008): JsonlObserver als Default-Listener.

Vorher war services/video_pipeline/observability.py toter Code — kein
Aufrufer registrierte den Observer. Jetzt bekommt build_pipeline ohne
externen Listener automatisch einen JsonlObserver (Audit-Trail).
"""
import json


def test_build_pipeline_wires_jsonl_observer_by_default(tmp_path):
    from services.video_pipeline.app_integration import build_pipeline
    from services.video_pipeline.observability import JsonlObserver

    src = tmp_path / "x.mp4"
    src.write_bytes(b"\x00\x01\x02\x03")
    pipe, _ = build_pipeline(
        track_id=1, source_path=src, storage_dir=tmp_path / "store",
    )
    assert isinstance(pipe.listener, JsonlObserver)
    assert pipe.listener.log_path.name == "pipeline.events.jsonl"


def test_external_listener_not_overridden(tmp_path):
    from services.video_pipeline.app_integration import build_pipeline

    class _MyListener:
        def on_stage_started(self, *a, **k): pass
        def on_stage_done(self, *a, **k): pass
        def on_stage_failed(self, *a, **k): pass
        def on_pipeline_done(self, *a, **k): pass

    src = tmp_path / "x.mp4"
    src.write_bytes(b"\x00\x01\x02\x03")
    mine = _MyListener()
    pipe, _ = build_pipeline(
        track_id=1, source_path=src, storage_dir=tmp_path / "store",
        listener=mine,
    )
    assert pipe.listener is mine


def test_observer_writes_events(tmp_path):
    from services.video_pipeline.observability import JsonlObserver
    from services.video_pipeline.stages.base import StageResult

    obs = JsonlObserver(tmp_path / "ev.jsonl")
    obs.on_stage_started(1, "scene_detect")
    obs.on_stage_done(1, StageResult(
        stage_id="scene_detect", status="done", duration_s=0.5,
        metrics={"scene_count": 3}))
    obs.on_pipeline_done(1)

    lines = (tmp_path / "ev.jsonl").read_text().strip().splitlines()
    events = [json.loads(ln)["event"] for ln in lines]
    assert events == ["stage_started", "stage_done", "pipeline_done"]
