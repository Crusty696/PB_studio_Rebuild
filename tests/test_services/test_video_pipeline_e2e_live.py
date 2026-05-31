"""Gegenpruefung E2E — Pipeline-Lauf mit echten Modellen.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19

Marker ``live_gpu``: laed echte SigLIP + RAFT Modelle.
Synthetisches 2s Video, alle Stages durch, Checkpoint + Status validiert.

Aufruf: ``pytest tests/test_services/test_video_pipeline_e2e_live.py -m live_gpu``
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest


pytestmark = [
    pytest.mark.live_gpu,
    pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg missing"),
]


@pytest.fixture
def synth_2scene_video(tmp_path: Path) -> Path:
    """4s 2-Szenen-Video."""
    out = tmp_path / "e2e_src.mp4"
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    ff = shutil.which("ffmpeg")
    for src, gen in [(a, "testsrc"), (b, "smptebars")]:
        subprocess.run(
            [ff, "-y", "-f", "lavfi",
             "-i", f"{gen}=duration=2:size=320x240:rate=10",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)],
            check=True, capture_output=True, timeout=30,
        )
    concat = tmp_path / "c.txt"
    concat.write_text(f"file '{a}'\nfile '{b}'\n")
    subprocess.run(
        [ff, "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
         "-c", "copy", str(out)],
        check=True, capture_output=True, timeout=30,
    )
    return out


def test_e2e_full_pipeline_real_models(synth_2scene_video: Path, tmp_path: Path):
    """End-to-end Lauf inkl. echter SigLIP-Embeds + RAFT-Flow."""
    import torch
    if not torch.cuda.is_available():
        pytest.skip("no CUDA")

    from services.video_pipeline.orchestrator import VideoAnalysisPipeline
    from services.video_pipeline.primitives.resume_checkpoint import ResumeCheckpoint
    from services.video_pipeline.primitives.stream_hasher import stream_sha256
    from services.video_pipeline.stages.proxy_gen_stage import ProxyGenStage
    from services.video_pipeline.stages.scene_detect_stage import SceneDetectStage
    from services.video_pipeline.stages.keyframe_extract_stage import KeyframeExtractStage
    from services.video_pipeline.stages.siglip_embed_stage import SigLipEmbedStage
    from services.video_pipeline.stages.siglip_embed_service import SigLipEmbedService
    from services.video_pipeline.stages.raft_motion_stage import RaftMotionStage
    from services.video_pipeline.stages.raft_motion_service import RaftMotionService
    from services.video_pipeline.stages.vlm_caption_stage import VlmCaptionStage
    from services.video_pipeline.stages.cross_modal_stage import CrossModalStage
    from services.video_pipeline.status_reporter import StatusReporter
    from services.video_pipeline.observability import JsonlObserver

    storage = tmp_path / "storage"
    sha = stream_sha256(synth_2scene_video)
    cp = ResumeCheckpoint(
        storage / "checkpoint.json", track_id=1, stream_sha256=sha,
    )

    siglip = SigLipEmbedService(model_id="google/siglip-so400m-patch14-384")
    raft = RaftMotionService(variant="raft_small", iter_count=4, resolution_scale=0.5)

    # Audio-Outputs simulieren
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    (audio_dir / "beats.json").write_text(json.dumps([0.5, 1.0, 1.5, 2.05, 2.5, 3.0]))

    stage_ids = ["proxy_gen", "scene_detect", "keyframe_extract",
                 "siglip_embed", "raft_motion", "vlm_caption", "cross_modal"]
    reporter = StatusReporter(stage_ids)
    observer = JsonlObserver(storage / "events.jsonl")

    class _Multi:
        def __init__(self, *ls): self.ls = ls
        def on_stage_started(self, *a, **k):
            for l in self.ls: l.on_stage_started(*a, **k)
        def on_stage_done(self, *a, **k):
            for l in self.ls: l.on_stage_done(*a, **k)
        def on_stage_failed(self, *a, **k):
            for l in self.ls: l.on_stage_failed(*a, **k)
        def on_pipeline_done(self, *a, **k):
            for l in self.ls: l.on_pipeline_done(*a, **k)

    pipe = VideoAnalysisPipeline(
        track_id=1, source_path=synth_2scene_video, storage_dir=storage,
        stages=[
            ProxyGenStage(max_width=160, bitrate="200k"),
            SceneDetectStage(),
            KeyframeExtractStage(mode="mid"),
            SigLipEmbedStage(service=siglip, batch_size=2),
            RaftMotionStage(service=raft, sample_rate_s=1.0),
            VlmCaptionStage(),                              # Stub
            CrossModalStage(audio_outputs_dir=audio_dir),
        ],
        checkpoint=cp,
        listener=_Multi(reporter, observer),
    )

    result = pipe.run()

    # === Assertions ===
    assert result.failed_count == 0, (
        f"Stages failed: {[r.error for r in result.stage_results if r.status == 'failed']}"
    )

    # Erwartete Artefakte
    assert (storage / "proxy.mp4").exists()
    assert (storage / "scenes.json").exists()
    assert (storage / "keyframes.json").exists()
    assert (storage / "embeddings.npy").exists()
    assert (storage / "motion.json").exists()
    assert (storage / "captions.json").exists()
    assert (storage / "cut_plan.json").exists()

    # SigLIP-Embeds Shape
    embeds = np.load(storage / "embeddings.npy")
    assert embeds.shape[1] == 1152  # so400m-Dim

    # Motion-JSON nicht leer
    motion = json.loads((storage / "motion.json").read_text())
    assert len(motion) >= 1
    assert "mean_magnitude" in motion[0]

    # Checkpoint persistiert
    assert (storage / "checkpoint.json").exists()
    cp_data = json.loads((storage / "checkpoint.json").read_text())
    assert cp_data["track_id"] == 1
    done_stages = [sid for sid, s in cp_data["stages"].items() if s["status"] == "done"]
    assert "scene_detect" in done_stages
    assert "siglip_embed" in done_stages

    # Status-Reporter
    summary = reporter.progress_summary()
    assert summary["done"] >= 6  # mind. 6 von 7 done

    # JSONL Observer
    log_lines = (storage / "events.jsonl").read_text().strip().split("\n")
    assert len(log_lines) >= len(stage_ids) * 2  # start + done pro Stage
    events = [json.loads(l) for l in log_lines]
    assert events[-1]["event"] == "pipeline_done"

    # Cleanup
    siglip.unload()
    raft.unload()


def test_raft_real_model_non_divisible_by_8():
    """B-440: RAFT mit echtem Modell auf nicht-/8 Frame -> kein ValueError.

    Schliesst den Blindspot des e2e-Tests, der nur /8-teilbare 320x240-Frames
    nutzte. Vor dem Fix: ValueError "feature encoder should downsample H and W by 8".
    """
    import torch
    if not torch.cuda.is_available():
        pytest.skip("no CUDA")
    import numpy as np
    from services.video_pipeline.stages.raft_motion_service import RaftMotionService

    svc = RaftMotionService(variant="raft_small", iter_count=4)
    h, w = 158, 238  # nicht durch 8 teilbar (reale Aufloesung)
    f1 = np.zeros((h, w, 3), dtype=np.uint8)
    f2 = (np.ones((h, w, 3)) * 30).astype(np.uint8)

    flow = svc.compute_flow(f1, f2)

    assert flow.shape == (h, w, 2)
    svc.unload()
