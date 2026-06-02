"""Phase 6 Brain V3 performance profile.

Misst:
- Pacing-Run ohne/mit Brain V3 ueber vorhandenen Phase-4-Smoke
- EmbeddingScheduler Queue-/Persistenz-Overhead mit Fake-Embedder

Hinweis: Embedding-Profil nutzt bewusst Fake-Embedder. Es misst Queue,
Signals und Cache-Store, nicht CLAP/SigLIP GPU-Inferenz.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * (pct / 100.0)
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    frac = pos - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def _summary(values: list[float]) -> dict[str, float]:
    return {
        "min": min(values) if values else 0.0,
        "median": _percentile(values, 50.0),
        "p95": _percentile(values, 95.0),
        "max": max(values) if values else 0.0,
    }


def _ensure_qt_app_for_profile():
    """Return a Qt app without blocking later QApplication-based tests."""
    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication.instance()
    if app is not None:
        return app

    try:
        from PySide6.QtWidgets import QApplication

        return QApplication([])
    except Exception:
        return QCoreApplication([])


def _run_pacing_smoke_once() -> dict[str, Any]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [sys.executable, "scripts/spike_brain_v3_pacing_smoke.py"],
        cwd=str(PROJECT_ROOT),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout + proc.stderr)
    return json.loads(proc.stdout)


def run_pacing_profile(iterations: int = 5) -> dict[str, Any]:
    samples = []
    overhead = []
    learning = []
    baseline = []
    brain = []

    for _idx in range(iterations):
        data = _run_pacing_smoke_once()
        timings = data["timings_ms"]
        sample = {
            "pacing_baseline_ms": timings["pacing_baseline"],
            "pacing_brain_v3_ms": timings["pacing_brain_v3"],
            "pacing_overhead_ms": timings["pacing_overhead"],
            "learning_session_ms": timings["learning_session"],
            "ok": bool(data["ok"]),
        }
        samples.append(sample)
        baseline.append(sample["pacing_baseline_ms"])
        brain.append(sample["pacing_brain_v3_ms"])
        overhead.append(sample["pacing_overhead_ms"])
        learning.append(sample["learning_session_ms"])

    return {
        "iterations": iterations,
        "samples": samples,
        "pacing_baseline_ms": _summary(baseline),
        "pacing_brain_v3_ms": _summary(brain),
        "pacing_overhead_ms": _summary(overhead),
        "learning_session_ms": _summary(learning),
        "checks": {
            "all_samples_ok": all(s["ok"] for s in samples),
            "pacing_overhead_p95_under_800ms": _summary(overhead)["p95"] < 800.0,
            "learning_session_p95_under_2s": _summary(learning)["p95"] < 2000.0,
        },
    }


def run_embedding_queue_profile(
    n_jobs: int = 20,
    fake_work_seconds: float = 0.02,
) -> dict[str, Any]:
    from services.brain_v3.embedding_scheduler import (
        EmbeddingScheduler,
        reset_default_scheduler_for_tests,
    )
    from services.brain_v3.gpu_serializer import (
        GpuSerializer,
        reset_default_serializer_for_tests,
    )
    from services.brain_v3.storage.embedding_cache import EmbeddingCache

    tmp_root = Path(tempfile.mkdtemp(prefix="pb-brain-v3-perf-"))
    os.environ["APPDATA"] = str(tmp_root / "Roaming")
    app = _ensure_qt_app_for_profile()
    reset_default_scheduler_for_tests()
    reset_default_serializer_for_tests()
    cache = EmbeddingCache()
    latencies: dict[str, float] = {}
    completed_at: dict[str, float] = {}

    def fake_embedder(task, progress_cb, serializer):
        time.sleep(fake_work_seconds)
        progress_cb(0.5, "fake-profile")
        return {
            "embedding": np.zeros(8, dtype=np.float32),
            "model_name": "profile/fake",
            "model_version": "0.0",
        }

    scheduler = EmbeddingScheduler(
        n_workers=1,
        cache=cache,
        embedder_factory=fake_embedder,
        serializer=GpuSerializer(empty_cache_on_release=False),
    )
    submitted_at: dict[str, float] = {}
    try:
        scheduler.start()
        start = time.perf_counter()
        for idx in range(n_jobs):
            media_hash = f"{idx:064x}"
            submitted_at[media_hash] = time.perf_counter()
            scheduler.submit_path(
                media_hash=media_hash,
                source_path=tmp_root / f"fake_{idx}.mp4",
                media_type="video",
            )

        deadline = time.perf_counter() + max(10.0, n_jobs * fake_work_seconds * 5)
        while time.perf_counter() < deadline:
            for media_hash in list(submitted_at):
                if media_hash in completed_at:
                    continue
                entry = cache.lookup(media_hash, "profile/fake", "0.0")
                if entry is not None:
                    completed_at[media_hash] = time.perf_counter()
                    latencies[media_hash] = (
                        completed_at[media_hash] - submitted_at[media_hash]
                    ) * 1000.0
            if len(completed_at) >= n_jobs:
                break
            app.processEvents()
            time.sleep(0.005)

        elapsed = time.perf_counter() - start
    finally:
        scheduler.request_stop(timeout_ms=5000)
        reset_default_scheduler_for_tests()
        reset_default_serializer_for_tests()

    latency_values = list(latencies.values())
    completed = len(completed_at)
    return {
        "tmp_root": str(tmp_root),
        "submitted": n_jobs,
        "completed": completed,
        "elapsed_s": elapsed,
        "throughput_jobs_per_s": completed / elapsed if elapsed > 0 else 0.0,
        "median_latency_ms": _percentile(latency_values, 50.0),
        "p95_latency_ms": _percentile(latency_values, 95.0),
        "max_latency_ms": max(latency_values) if latency_values else 0.0,
        "checks": {
            "all_jobs_completed": completed == n_jobs,
            "throughput_positive": completed > 0 and elapsed > 0,
        },
    }


def run(out_root: Path, iterations: int, n_jobs: int) -> dict[str, Any]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = out_root / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "out_dir": str(out_dir),
        "pacing": run_pacing_profile(iterations=iterations),
        "embedding_queue": run_embedding_queue_profile(n_jobs=n_jobs),
    }
    result["status"] = (
        "ok"
        if (
            result["pacing"]["checks"]["all_samples_ok"]
            and result["pacing"]["checks"]["pacing_overhead_p95_under_800ms"]
            and result["embedding_queue"]["checks"]["all_jobs_completed"]
        )
        else "fail"
    )
    (out_dir / "results.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--n-jobs", type=int, default=20)
    parser.add_argument(
        "--out-root",
        default="outputs/spike_brain_v3_performance_profile",
    )
    args = parser.parse_args()
    result = run(Path(args.out_root), iterations=args.iterations, n_jobs=args.n_jobs)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
