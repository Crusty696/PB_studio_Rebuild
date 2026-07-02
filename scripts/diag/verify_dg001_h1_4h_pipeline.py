"""DG-001 H1.3: 4h-Produktions-Video-Pipeline mit persistentem Beleg."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback
from typing import Any

from dotenv import load_dotenv


APP_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = Path(
    os.environ.get(
        "PB_DG001_H1_EVIDENCE_DIR",
        str(APP_ROOT / "test-report" / "dg001-h1-4h-20260623"),
    )
)
INPUT_PATH = Path(
    os.environ.get(
        "PB_DG001_H1_INPUT_PATH",
        str(EVIDENCE_DIR / "input_4h_real_pb_media.mp4"),
    )
)
STORAGE_DIR = EVIDENCE_DIR / "pipeline_storage"
EVENTS_PATH = EVIDENCE_DIR / "stage_events.jsonl"
SAMPLES_PATH = EVIDENCE_DIR / "resource_samples.jsonl"
RESULT_PATH = EVIDENCE_DIR / "result.json"
LOG_PATH = EVIDENCE_DIR / "h1_3.log"
TRACK_ID = 999_998

load_dotenv(APP_ROOT / ".env")
os.environ["PATH"] = str(APP_ROOT / "bin") + os.pathsep + os.environ.get("PATH", "")
os.environ["PB_REQUIRE_NVENC"] = "1"
sys.path.insert(0, str(APP_ROOT))


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        handle.flush()


def _cuda_memory_probe() -> dict[str, Any]:
    try:
        import torch

        free_bytes, total_bytes = torch.cuda.mem_get_info(0)
        return {
            "torch_free_mib": round(free_bytes / 1024 / 1024, 2),
            "torch_total_mib": round(total_bytes / 1024 / 1024, 2),
            "torch_allocated_mib": round(
                torch.cuda.memory_allocated(0) / 1024 / 1024, 2
            ),
            "torch_reserved_mib": round(
                torch.cuda.memory_reserved(0) / 1024 / 1024, 2
            ),
        }
    except Exception as exc:
        return {"torch_probe_error": f"{type(exc).__name__}: {exc}"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _probe(path: Path) -> dict[str, Any]:
    output = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size,bit_rate:stream=index,codec_type,codec_name,width,height,"
            "avg_frame_rate,nb_frames,sample_rate,channels",
            "-of",
            "json",
            str(path),
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    return json.loads(output)


class EvidenceListener:
    def __init__(self, started: float):
        self.started = started

    def _record(self, event: str, **payload: Any) -> None:
        _append_jsonl(
            EVENTS_PATH,
            {
                "timestamp": _now(),
                "elapsed_s": time.monotonic() - self.started,
                "event": event,
                **payload,
            },
        )

    def on_stage_started(self, track_id: int, stage_id: str) -> None:
        self._record(
            "stage_started",
            track_id=track_id,
            stage_id=stage_id,
            cuda_memory=_cuda_memory_probe(),
        )

    def on_stage_done(self, track_id: int, result: Any) -> None:
        self._record(
            "stage_done",
            track_id=track_id,
            stage_id=result.stage_id,
            status=result.status,
            duration_s=result.duration_s,
            metrics=result.metrics,
            artifacts={key: str(value) for key, value in result.artifacts.items()},
            error=result.error,
        )

    def on_stage_failed(self, track_id: int, result: Any) -> None:
        self._record(
            "stage_failed",
            track_id=track_id,
            stage_id=result.stage_id,
            status=result.status,
            duration_s=result.duration_s,
            metrics=result.metrics,
            error=result.error,
        )

    def on_pipeline_done(self, track_id: int) -> None:
        self._record("pipeline_done", track_id=track_id)


def _sample_resources(stop: threading.Event, started: float) -> None:
    try:
        import psutil

        process = psutil.Process()
    except Exception:
        psutil = None
        process = None

    while not stop.is_set():
        sample: dict[str, Any] = {
            "timestamp": _now(),
            "elapsed_s": time.monotonic() - started,
        }
        try:
            output = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            ).strip()
            name, util, used, total, temperature = [
                part.strip() for part in output.split(",")
            ]
            sample["gpu"] = {
                "name": name,
                "utilization_percent": int(util),
                "memory_used_mib": int(used),
                "memory_total_mib": int(total),
                "temperature_c": int(temperature),
            }
        except Exception as exc:
            sample["gpu_error"] = f"{type(exc).__name__}: {exc}"

        if psutil is not None and process is not None:
            memory = psutil.virtual_memory()
            sample["process_rss_mib"] = round(
                process.memory_info().rss / 1024 / 1024, 2
            )
            sample["system_memory"] = {
                "used_mib": round(memory.used / 1024 / 1024, 2),
                "available_mib": round(memory.available / 1024 / 1024, 2),
                "percent": memory.percent,
            }

        _append_jsonl(SAMPLES_PATH, sample)
        stop.wait(10.0)


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact_summary() -> dict[str, Any]:
    names = (
        "proxy.mp4",
        "scenes.json",
        "keyframes.json",
        "embeddings.npy",
        "motion.json",
        "captions.json",
        "cut_plan.json",
        "checkpoint.json",
    )
    summary: dict[str, Any] = {}
    for name in names:
        path = STORAGE_DIR / name
        summary[name] = {
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
        }
    return summary


def _coverage_summary() -> dict[str, Any]:
    import numpy as np

    scenes = _read_json(STORAGE_DIR / "scenes.json") or []
    keyframes = _read_json(STORAGE_DIR / "keyframes.json") or []
    motion = _read_json(STORAGE_DIR / "motion.json") or []
    captions = _read_json(STORAGE_DIR / "captions.json") or []
    cuts = _read_json(STORAGE_DIR / "cut_plan.json") or []
    embeddings_path = STORAGE_DIR / "embeddings.npy"
    embedding_shape = (
        list(np.load(embeddings_path, mmap_mode="r").shape)
        if embeddings_path.exists()
        else None
    )
    return {
        "scene_count": len(scenes),
        "keyframe_count": len(keyframes),
        "embedding_shape": embedding_shape,
        "motion_pair_count": len(motion),
        "caption_count": len(captions),
        "cut_suggestion_count": len(cuts),
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, mode="a", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logger = logging.getLogger("dg001.h1.3")
    started = time.monotonic()
    started_at = _now()
    stop_sampling = threading.Event()
    sampler = threading.Thread(
        target=_sample_resources,
        args=(stop_sampling, started),
        name="dg001-h1-resource-sampler",
        daemon=True,
    )
    services: tuple[Any, Any] | None = None
    pipeline_result = None
    error = None

    try:
        import torch

        if not INPUT_PATH.is_file():
            raise FileNotFoundError(INPUT_PATH)
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable")
        gpu_name = torch.cuda.get_device_name(0)
        if gpu_name != "NVIDIA GeForce GTX 1060":
            raise RuntimeError(f"unexpected GPU: {gpu_name}")

        probe = _probe(INPUT_PATH)
        duration_s = float(probe["format"]["duration"])
        if duration_s < 14_399:
            raise RuntimeError(f"input shorter than 4h tolerance: {duration_s}")

        input_sha256 = _sha256(INPUT_PATH)
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        audio_dir = STORAGE_DIR / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        beats_path = audio_dir / "beats.json"
        if not beats_path.exists():
            beats_path.write_text(
                json.dumps([float(value) for value in range(0, 14_401, 2)]),
                encoding="utf-8",
            )

        EVENTS_PATH.touch(exist_ok=True)
        SAMPLES_PATH.touch(exist_ok=True)
        _append_jsonl(
            EVENTS_PATH,
            {
                "timestamp": started_at,
                "elapsed_s": 0.0,
                "event": "run_started",
                "input": str(INPUT_PATH),
                "input_sha256": input_sha256,
                "input_probe": probe,
                "gpu": gpu_name,
            },
        )
        sampler.start()

        from services.video_pipeline.app_integration import build_pipeline

        pipeline, services = build_pipeline(
            TRACK_ID,
            INPUT_PATH,
            STORAGE_DIR,
            raft_variant="raft_small",
            listener=EvidenceListener(started),
        )
        pipeline_result = pipeline.run()
        logger.info(
            "Pipeline beendet: completed=%s failed=%s cancelled=%s",
            pipeline_result.completed_count,
            pipeline_result.failed_count,
            pipeline_result.cancelled,
        )
    except BaseException as exc:
        error = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        logger.exception("DG-001 H1.3 fehlgeschlagen")
    finally:
        if services is not None:
            for service in services:
                try:
                    service.unload()
                except Exception:
                    logger.exception("Service-Unload fehlgeschlagen")
        stop_sampling.set()
        if sampler.is_alive():
            sampler.join(timeout=20)

    artifacts = _artifact_summary()
    coverage = _coverage_summary()
    stage_results = []
    if pipeline_result is not None:
        stage_results = [
            {
                "stage_id": item.stage_id,
                "status": item.status,
                "duration_s": item.duration_s,
                "metrics": item.metrics,
                "artifacts": {
                    key: str(value) for key, value in item.artifacts.items()
                },
                "error": item.error,
            }
            for item in pipeline_result.stage_results
        ]
    required_artifacts = (
        "proxy.mp4",
        "scenes.json",
        "keyframes.json",
        "embeddings.npy",
        "motion.json",
        "captions.json",
        "cut_plan.json",
    )
    passed = (
        error is None
        and pipeline_result is not None
        and pipeline_result.failed_count == 0
        and not pipeline_result.cancelled
        and all(artifacts[name]["exists"] for name in required_artifacts)
        and coverage["motion_pair_count"] >= 14_000
    )
    summary = {
        "gate": "DG-001 H1.3",
        "status": "pass" if passed else "fail",
        "started_at": started_at,
        "ended_at": _now(),
        "wall_s": time.monotonic() - started,
        "input_path": str(INPUT_PATH),
        "input_sha256": _sha256(INPUT_PATH) if INPUT_PATH.exists() else None,
        "input_probe": _probe(INPUT_PATH) if INPUT_PATH.exists() else None,
        "storage_dir": str(STORAGE_DIR),
        "stage_results": stage_results,
        "artifacts": artifacts,
        "coverage": coverage,
        "error": error,
    }
    RESULT_PATH.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _append_jsonl(
        EVENTS_PATH,
        {
            "timestamp": summary["ended_at"],
            "elapsed_s": summary["wall_s"],
            "event": "run_finished",
            "status": summary["status"],
            "result_path": str(RESULT_PATH),
        },
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
