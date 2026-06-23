"""DG-001 H3: echte parallele Demucs- und Video-Modellpipeline auf CUDA."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import traceback

from dotenv import load_dotenv


APP_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = APP_ROOT / "test-report" / "dg001-h3-concurrency-20260623"
RUN_ID = time.strftime("%Y%m%d-%H%M%S")
RUN_DIR = EVIDENCE_DIR / RUN_ID
PROJECT_ROOT = RUN_DIR / "project"
AUDIO_PATH = RUN_DIR / "h3_audio.wav"

load_dotenv(APP_ROOT / ".env")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["PATH"] = str(APP_ROOT / "bin") + os.pathsep + os.environ.get("PATH", "")
sys.path.insert(0, str(APP_ROOT))


def _make_video(path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg missing")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=4:size=320x240:rate=10",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )


def _make_audio(path: Path) -> int:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg missing")
    seed = time.time_ns() % 2_147_483_647
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=110:duration=8:sample_rate=44100",
            "-f",
            "lavfi",
            "-i",
            f"anoisesrc=color=pink:duration=8:sample_rate=44100:seed={seed}",
            "-filter_complex",
            "[0:a][1:a]amix=inputs=2:weights='1 0.08',pan=stereo|c0=c0|c1=c0",
            "-c:a",
            "pcm_s16le",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    return seed


def _prepare_audio_track() -> int:
    from database.session import set_project

    PROJECT_ROOT.mkdir(parents=True, exist_ok=True)
    set_project(PROJECT_ROOT)

    from database import AudioTrack, Project, engine, init_db
    from sqlalchemy.orm import Session

    init_db()
    with Session(engine) as session:
        project = session.query(Project).filter(Project.deleted_at.is_(None)).first()
        if project is None:
            project = Project(
                name="DG001 H3 Concurrency",
                path=str(PROJECT_ROOT),
                resolution="1920x1080",
                fps=30.0,
            )
            session.add(project)
            session.commit()
        project_id = project.id
        track = session.query(AudioTrack).filter(AudioTrack.file_path == str(AUDIO_PATH)).first()
        if track is not None:
            return track.id

    from services.ingest_service import ingest_audio

    result = ingest_audio(str(AUDIO_PATH), project_id=project_id)
    if result is None:
        raise RuntimeError("audio ingest returned None")
    with Session(engine) as session:
        track = session.query(AudioTrack).filter(AudioTrack.file_path == str(AUDIO_PATH)).first()
        if track is None:
            raise RuntimeError("ingested audio track not found")
        return track.id


def _run_audio(track_id: int, record: dict) -> None:
    from services.audio_pipeline.context import PipelineContext
    from services.audio_pipeline.orchestrator import AudioAnalysisPipeline
    from services.audio_pipeline.stages import build_default_stages

    started = time.monotonic()
    stage_events: list[dict] = []
    context = PipelineContext(track_id=track_id, original_path=str(AUDIO_PATH))
    pipeline = AudioAnalysisPipeline(build_default_stages())
    pipeline.stage_started.connect(
        lambda name: stage_events.append(
            {"event": "start", "stage": name, "t": time.monotonic() - started}
        )
    )
    pipeline.stage_done.connect(
        lambda name, payload: stage_events.append(
            {
                "event": "done",
                "stage": name,
                "t": time.monotonic() - started,
                "payload": str(payload),
            }
        )
    )
    failures: list[dict] = []
    pipeline.stage_failed.connect(
        lambda name, message: failures.append(
            {"stage": name, "message": message, "t": time.monotonic() - started}
        )
    )
    try:
        pipeline._run_stages(context)
        record.update(
            {
                "ok": not failures,
                "elapsed_s": time.monotonic() - started,
                "failures": failures,
                "stage_events": stage_events,
                "result_keys": sorted(context.results),
            }
        )
    except BaseException as exc:
        record.update(
            {
                "ok": False,
                "elapsed_s": time.monotonic() - started,
                "exception": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
                "stage_events": stage_events,
            }
        )


def _run_video(video_path: Path, record: dict) -> None:
    from services.video_pipeline.orchestrator import VideoAnalysisPipeline
    from services.video_pipeline.stages.cross_modal_stage import CrossModalStage
    from services.video_pipeline.stages.keyframe_extract_stage import KeyframeExtractStage
    from services.video_pipeline.stages.proxy_gen_stage import ProxyGenStage
    from services.video_pipeline.stages.raft_motion_service import RaftMotionService
    from services.video_pipeline.stages.raft_motion_stage import RaftMotionStage
    from services.video_pipeline.stages.scene_detect_stage import SceneDetectStage
    from services.video_pipeline.stages.siglip_embed_service import SigLipEmbedService
    from services.video_pipeline.stages.siglip_embed_stage import SigLipEmbedStage
    from services.video_pipeline.stages.vlm_caption_stage import VlmCaptionStage

    started = time.monotonic()
    storage = RUN_DIR / "video_storage"
    audio_outputs = RUN_DIR / "video_audio_outputs"
    audio_outputs.mkdir(parents=True, exist_ok=True)
    (audio_outputs / "beats.json").write_text(
        json.dumps([0.5, 1.0, 1.5, 2.0, 2.5, 3.0]),
        encoding="utf-8",
    )
    siglip = SigLipEmbedService(model_id="google/siglip-so400m-patch14-384")
    raft = RaftMotionService(variant="raft_small", iter_count=4, resolution_scale=0.5)
    try:
        pipeline = VideoAnalysisPipeline(
            track_id=999999,
            source_path=video_path,
            storage_dir=storage,
            stages=[
                ProxyGenStage(max_width=160, bitrate="200k"),
                SceneDetectStage(),
                KeyframeExtractStage(mode="mid"),
                SigLipEmbedStage(service=siglip, batch_size=2),
                RaftMotionStage(service=raft, sample_rate_s=1.0),
                VlmCaptionStage(),
                CrossModalStage(audio_outputs_dir=audio_outputs),
            ],
        )
        result = pipeline.run()
        artifacts = {
            name: (storage / name).exists()
            for name in (
                "proxy.mp4",
                "scenes.json",
                "keyframes.json",
                "embeddings.npy",
                "motion.json",
                "captions.json",
                "cut_plan.json",
            )
        }
        record.update(
            {
                "ok": result.failed_count == 0 and all(artifacts.values()),
                "elapsed_s": time.monotonic() - started,
                "completed_count": result.completed_count,
                "failed_count": result.failed_count,
                "cancelled": result.cancelled,
                "stages": [
                    {
                        "stage": item.stage_id,
                        "status": item.status,
                        "error": item.error,
                        "duration_s": item.duration_s,
                    }
                    for item in result.stage_results
                ],
                "artifacts": artifacts,
            }
        )
    except BaseException as exc:
        record.update(
            {
                "ok": False,
                "elapsed_s": time.monotonic() - started,
                "exception": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }
        )
    finally:
        siglip.unload()
        raft.unload()


def _sample_gpu(stop: threading.Event, samples: list[dict], started: float) -> None:
    while not stop.wait(1.0):
        try:
            output = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=timestamp,utilization.gpu,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                timeout=5,
            ).strip()
            timestamp, util, used, total = [part.strip() for part in output.split(",")]
            samples.append(
                {
                    "t": time.monotonic() - started,
                    "timestamp": timestamp,
                    "utilization_percent": int(util),
                    "memory_used_mib": int(used),
                    "memory_total_mib": int(total),
                }
            )
        except Exception as exc:
            samples.append({"t": time.monotonic() - started, "sample_error": str(exc)})


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    log_path = RUN_DIR / "h3.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, mode="w", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    from PySide6.QtWidgets import QApplication
    import torch

    app = QApplication.instance() or QApplication([])
    del app
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable")
    if torch.cuda.get_device_name(0) != "NVIDIA GeForce GTX 1060":
        raise RuntimeError(f"unexpected GPU: {torch.cuda.get_device_name(0)}")

    video_path = RUN_DIR / "h3_video.mp4"
    audio_seed = _make_audio(AUDIO_PATH)
    _make_video(video_path)
    track_id = _prepare_audio_track()

    audio_result: dict = {}
    video_result: dict = {}
    gpu_samples: list[dict] = []
    started = time.monotonic()
    stop_sampling = threading.Event()
    sampler = threading.Thread(
        target=_sample_gpu,
        args=(stop_sampling, gpu_samples, started),
        name="h3-gpu-sampler",
        daemon=True,
    )
    audio_thread = threading.Thread(
        target=_run_audio,
        args=(track_id, audio_result),
        name="h3-audio-demucs",
    )
    video_thread = threading.Thread(
        target=_run_video,
        args=(video_path, video_result),
        name="h3-video-pipeline",
    )

    sampler.start()
    audio_thread.start()
    video_thread.start()
    audio_thread.join(timeout=900)
    video_thread.join(timeout=900)
    stop_sampling.set()
    sampler.join(timeout=10)

    wall_s = time.monotonic() - started
    summary = {
        "gate": "DG-001 H3",
        "run_id": RUN_ID,
        "run_dir": str(RUN_DIR),
        "audio_seed": audio_seed,
        "gpu": torch.cuda.get_device_name(0),
        "cuda": True,
        "wall_s": wall_s,
        "threads_alive": {
            "audio": audio_thread.is_alive(),
            "video": video_thread.is_alive(),
        },
        "audio": audio_result,
        "video": video_result,
        "gpu_samples": gpu_samples,
    }
    summary["pass"] = (
        not audio_thread.is_alive()
        and not video_thread.is_alive()
        and audio_result.get("ok") is True
        and video_result.get("ok") is True
    )
    (RUN_DIR / "result.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (EVIDENCE_DIR / "latest.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
