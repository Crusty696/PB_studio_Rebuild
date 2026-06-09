from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = Path(__file__).resolve().parent
SRC = REPORT_DIR / "b333_src.mp4"
OUT = REPORT_DIR / "b333_live_gpu_result.json"


def mem(label: str) -> dict:
    import torch

    if torch.cuda.is_available():
        return {
            "label": label,
            "allocated_mb": round(torch.cuda.memory_allocated() / 1024 / 1024, 1),
            "reserved_mb": round(torch.cuda.memory_reserved() / 1024 / 1024, 1),
            "max_reserved_mb": round(torch.cuda.max_memory_reserved() / 1024 / 1024, 1),
        }
    return {"label": label, "allocated_mb": 0.0, "reserved_mb": 0.0, "max_reserved_mb": 0.0}


def make_video() -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg missing")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=2:size=320x240:rate=10",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(SRC),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )


def main() -> int:
    import sys

    sys.path.insert(0, str(ROOT))

    import torch
    from services.video_pipeline.observability import JsonlObserver
    from services.video_pipeline.orchestrator import VideoAnalysisPipeline
    from services.video_pipeline.primitives.resume_checkpoint import ResumeCheckpoint
    from services.video_pipeline.primitives.stream_hasher import stream_sha256
    from services.video_pipeline.stages.cross_modal_stage import CrossModalStage
    from services.video_pipeline.stages.keyframe_extract_stage import KeyframeExtractStage
    from services.video_pipeline.stages.proxy_gen_stage import ProxyGenStage
    from services.video_pipeline.stages.raft_motion_service import RaftMotionService
    from services.video_pipeline.stages.raft_motion_stage import RaftMotionStage
    from services.video_pipeline.stages.scene_detect_stage import SceneDetectStage
    from services.video_pipeline.stages.siglip_embed_service import SigLipEmbedService
    from services.video_pipeline.stages.siglip_embed_stage import SigLipEmbedStage
    from services.video_pipeline.stages.vlm_caption_stage import VlmCaptionStage
    from services.video_pipeline.status_reporter import StatusReporter

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA missing")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    make_video()
    storage = REPORT_DIR / "storage"
    if storage.exists():
        shutil.rmtree(storage)
    storage.mkdir()
    audio_dir = REPORT_DIR / "audio"
    audio_dir.mkdir(exist_ok=True)
    (audio_dir / "beats.json").write_text(json.dumps([0.5, 1.0, 1.5]), encoding="utf-8")

    measurements: list[dict] = []

    def capture(label: str) -> None:
        torch.cuda.empty_cache()
        measurements.append(mem(label))

    class _MeasuredStage:
        def __init__(self, stage):
            self.stage = stage
            self.stage_id = stage.stage_id

        def run(self, *args, **kwargs):
            capture(f"start_{self.stage_id}")
            return self.stage.run(*args, **kwargs)

        def unload(self):
            capture(f"before_unload_{self.stage_id}")
            unload = getattr(self.stage, "unload", None)
            if callable(unload):
                unload()
            capture(f"after_unload_{self.stage_id}")

    class _Multi:
        def __init__(self, *listeners):
            self.listeners = listeners

        def on_stage_started(self, *args, **kwargs):
            for listener in self.listeners:
                listener.on_stage_started(*args, **kwargs)

        def on_stage_done(self, *args, **kwargs):
            for listener in self.listeners:
                listener.on_stage_done(*args, **kwargs)

        def on_stage_failed(self, *args, **kwargs):
            for listener in self.listeners:
                listener.on_stage_failed(*args, **kwargs)

        def on_pipeline_done(self, *args, **kwargs):
            for listener in self.listeners:
                listener.on_pipeline_done(*args, **kwargs)

    siglip = SigLipEmbedService(model_id="google/siglip-so400m-patch14-384")
    raft = RaftMotionService(variant="raft_small", iter_count=4, resolution_scale=0.5)
    stages = [
        _MeasuredStage(ProxyGenStage(max_width=160, bitrate="200k")),
        _MeasuredStage(SceneDetectStage()),
        _MeasuredStage(KeyframeExtractStage(mode="mid")),
        _MeasuredStage(SigLipEmbedStage(service=siglip, batch_size=2)),
        _MeasuredStage(RaftMotionStage(service=raft, sample_rate_s=1.0)),
        _MeasuredStage(VlmCaptionStage()),
        _MeasuredStage(CrossModalStage(audio_outputs_dir=audio_dir)),
    ]

    reporter = StatusReporter([stage.stage_id for stage in stages])
    observer = JsonlObserver(storage / "events.jsonl")
    checkpoint = ResumeCheckpoint(
        storage / "checkpoint.json",
        track_id=1,
        stream_sha256=stream_sha256(SRC),
    )
    pipe = VideoAnalysisPipeline(
        track_id=1,
        source_path=SRC,
        storage_dir=storage,
        stages=stages,
        checkpoint=checkpoint,
        listener=_Multi(reporter, observer),
    )

    capture("baseline")
    start = time.monotonic()
    result = pipe.run()
    elapsed = round(time.monotonic() - start, 2)
    capture("final_cleanup")

    data = {
        "ok": result.failed_count == 0,
        "elapsed_sec": elapsed,
        "completed": result.completed_count,
        "failed": result.failed_count,
        "stage_results": [
            {"stage_id": r.stage_id, "status": r.status, "error": r.error}
            for r in result.stage_results
        ],
        "measurements": measurements,
    }
    OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")

    by_label = {m["label"]: m for m in measurements}
    before = by_label["before_unload_siglip_embed"]["allocated_mb"]
    after = by_label["after_unload_siglip_embed"]["allocated_mb"]
    raft_start = by_label["start_raft_motion"]["allocated_mb"]
    ok = result.failed_count == 0 and before > 500 and after < 200 and raft_start < 200
    print(json.dumps({"ok": ok, "before_siglip_mb": before, "after_siglip_mb": after, "raft_start_mb": raft_start}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
