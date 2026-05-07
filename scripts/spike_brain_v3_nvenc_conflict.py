"""Phase 6 Spike: NVENC + Brain-V3 GPU-Serializer conflict behavior.

Misst drei Dinge:
- render wartet auf laufenden Brain-V3-Serializer-Holder (CLAP/SigLIP-Pfad)
- render wartet auf alten GPU_EXECUTION_LOCK (Demucs/RAFT/BeatThis-Pfad)
- echter kurzer NVENC-Encode laeuft via convert_service.convert()

Das ist ein Lock-/NVENC-Smoke, kein voller CLAP/SigLIP-Modell-Inferenzlauf.
"""
from __future__ import annotations

import argparse
import json
import sys
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.brain_v3.gpu_serializer import (
    get_default_serializer,
    reset_default_serializer_for_tests,
)
from services.startup_checks import get_ffmpeg_bin


def measure_serializer_conflict(hold_seconds: float = 0.5) -> dict[str, Any]:
    """Proves render holder waits for an active Brain-V3 holder."""
    reset_default_serializer_for_tests()
    serializer = get_default_serializer()
    brain_entered = threading.Event()
    release_brain = threading.Event()
    render_wait_s: list[float] = []

    def brain_worker() -> None:
        with serializer.acquire("clap_embed_mix"):
            brain_entered.set()
            release_brain.wait(timeout=hold_seconds)

    def render_worker() -> None:
        brain_entered.wait(timeout=2.0)
        start = time.perf_counter()
        with serializer.acquire("render"):
            render_wait_s.append(time.perf_counter() - start)

    brain = threading.Thread(target=brain_worker, daemon=True)
    render = threading.Thread(target=render_worker, daemon=True)
    brain.start()
    assert brain_entered.wait(timeout=2.0)
    render.start()
    time.sleep(hold_seconds)
    release_brain.set()
    brain.join(timeout=2.0)
    render.join(timeout=2.0)

    wait = render_wait_s[0] if render_wait_s else 0.0
    return {
        "brain_holder": "clap_embed_mix",
        "render_holder": "render",
        "render_wait_s": wait,
        "serialized": wait >= max(0.01, hold_seconds * 0.6),
    }


def measure_legacy_gpu_lock_conflict(hold_seconds: float = 0.5) -> dict[str, Any]:
    """Proves render holder waits for legacy Demucs/RAFT GPU_EXECUTION_LOCK."""
    reset_default_serializer_for_tests()
    serializer = get_default_serializer()
    from services.model_manager import GPU_EXECUTION_LOCK

    entered = threading.Event()
    release_legacy = threading.Event()
    render_wait_s: list[float] = []

    def legacy_worker() -> None:
        with GPU_EXECUTION_LOCK:
            entered.set()
            release_legacy.wait(timeout=hold_seconds)

    def render_worker() -> None:
        entered.wait(timeout=2.0)
        start = time.perf_counter()
        with serializer.acquire("render"):
            render_wait_s.append(time.perf_counter() - start)

    legacy = threading.Thread(target=legacy_worker, daemon=True)
    render = threading.Thread(target=render_worker, daemon=True)
    legacy.start()
    assert entered.wait(timeout=2.0)
    render.start()
    time.sleep(hold_seconds)
    release_legacy.set()
    legacy.join(timeout=2.0)
    render.join(timeout=2.0)

    wait = render_wait_s[0] if render_wait_s else 0.0
    return {
        "legacy_holder": "demucs_or_raft",
        "render_holder": "render",
        "render_wait_s": wait,
        "serialized": wait >= max(0.01, hold_seconds * 0.6),
    }


def run_nvenc_encode(out_dir: Path) -> dict[str, Any]:
    """Runs a short real NVENC encode through convert_service.convert()."""
    from services.convert_service import convert, detect_nvenc

    ffmpeg = get_ffmpeg_bin()
    input_path = out_dir / "nvenc_conflict_input.mp4"
    output_path = out_dir / "nvenc_conflict_output.mp4"

    gen_cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "testsrc=duration=3:size=1280x720:rate=30",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        str(input_path),
    ]
    subprocess.run(gen_cmd, check=True, timeout=30)

    nvenc = detect_nvenc()
    start = time.perf_counter()
    result_path = convert(
        input_path,
        preset_name="edit_proxy",
        output_path=output_path,
        timeout=90.0,
    )
    duration = time.perf_counter() - start
    size = output_path.stat().st_size if output_path.exists() else 0
    return {
        "detect_nvenc": nvenc,
        "result_path": str(result_path),
        "duration_s": duration,
        "output_size_bytes": size,
        "encode_ok": output_path.exists() and size > 0,
    }


def run(out_root: Path) -> dict[str, Any]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = out_root / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "out_dir": str(out_dir),
        "serializer_conflict": measure_serializer_conflict(),
        "legacy_gpu_lock_conflict": measure_legacy_gpu_lock_conflict(),
        "nvenc_encode": run_nvenc_encode(out_dir),
    }
    results["status"] = (
        "ok"
        if (
            results["serializer_conflict"]["serialized"]
            and results["legacy_gpu_lock_conflict"]["serialized"]
            and results["nvenc_encode"]["encode_ok"]
        )
        else "fail"
    )
    (out_dir / "results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-root",
        default="outputs/spike_brain_v3_nvenc_conflict",
        help="Output root for timestamped results.",
    )
    args = parser.parse_args()
    results = run(Path(args.out_root))
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0 if results["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
