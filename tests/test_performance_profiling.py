#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Performance Profiling Test Suite for PB Studio

Measures and reports:
1. Model load/swap times (ModelManager)
2. RAFT optical flow throughput
3. SigLIP embedding generation speed
4. Beat detection performance
5. Export pipeline performance (libx264 vs NVENC)
6. UI frame times (if GUI available)

Usage:
    python -m pytest tests/test_performance_profiling.py -v -s
    python tests/test_performance_profiling.py  # Direct run for quick profiling
"""

from __future__ import annotations

import gc
import logging
import sys
import time
from pathlib import Path
from typing import Callable

import pytest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# Performance Metrics Collector
# ══════════════════════════════════════════════════════════════


class PerformanceMetrics:
    """Collects and reports performance metrics."""

    def __init__(self):
        self.metrics = {}
        self.metadata = {}

    def record(self, name: str, duration: float, metadata: dict | None = None):
        """Record a timing measurement."""
        if name not in self.metrics:
            self.metrics[name] = []
        self.metrics[name].append(duration)

        if metadata:
            if name not in self.metadata:
                self.metadata[name] = []
            self.metadata[name].append(metadata)

    def report(self):
        """Print comprehensive performance report."""
        print("\n" + "=" * 80)
        print("PB STUDIO PERFORMANCE PROFILING REPORT")
        print("=" * 80)
        print(f"{'Metric':<50s} | {'Avg':>8s} | {'Min':>8s} | {'Max':>8s} | {'Runs':>4s}")
        print("-" * 80)

        for name, times in sorted(self.metrics.items()):
            if not times:
                continue
            avg = sum(times) / len(times)
            min_t = min(times)
            max_t = max(times)
            count = len(times)
            print(f"{name:<50s} | {avg:>7.3f}s | {min_t:>7.3f}s | {max_t:>7.3f}s | {count:>4d}")

            # Print metadata if available
            if name in self.metadata and self.metadata[name]:
                for i, meta in enumerate(self.metadata[name]):
                    if meta:
                        meta_str = ", ".join(f"{k}={v}" for k, v in meta.items())
                        print(f"  └─ Run {i+1}: {meta_str}")

        print("=" * 80)

    def get_metric(self, name: str) -> list[float]:
        """Get all recorded timings for a metric."""
        return self.metrics.get(name, [])


@pytest.fixture(scope="module")
def perf_metrics():
    """Pytest fixture for performance metrics."""
    m = PerformanceMetrics()
    yield m
    m.report()


# ══════════════════════════════════════════════════════════════
# Test 1: Model Loading Performance
# ══════════════════════════════════════════════════════════════


def test_model_loading_performance(perf_metrics):
    """Profile ModelManager load/unload cycles.

    Tests:
    - SigLIP load time
    - RAFT load time
    - Model unload time
    - Model swap time (RAFT → SigLIP)
    """
    try:
        from services.model_manager import ModelManager
    except ImportError:
        pytest.skip("ModelManager not available")

    mm = ModelManager()

    # Test 1: Load SigLIP (vision embeddings)
    logger.info("Testing SigLIP load...")
    start = time.perf_counter()
    try:
        mm.load_siglip()
        elapsed = time.perf_counter() - start
        perf_metrics.record("model_load_siglip", elapsed, {"device": mm.device})
        logger.info(f"SigLIP loaded in {elapsed:.3f}s")
    except Exception as e:
        logger.warning(f"SigLIP load failed: {e}")
        pytest.skip(f"SigLIP not available: {e}")

    # Test 2: Unload
    logger.info("Testing model unload...")
    start = time.perf_counter()
    mm.unload()
    elapsed = time.perf_counter() - start
    perf_metrics.record("model_unload", elapsed)
    logger.info(f"Model unloaded in {elapsed:.3f}s")

    # Test 3: Load RAFT (optical flow)
    logger.info("Testing RAFT load...")
    start = time.perf_counter()
    try:
        mm.load_raft()
        elapsed = time.perf_counter() - start
        perf_metrics.record("model_load_raft", elapsed, {"device": mm.device})
        logger.info(f"RAFT loaded in {elapsed:.3f}s")
    except Exception as e:
        logger.warning(f"RAFT load failed: {e}")

    # Test 4: Model swap (RAFT → SigLIP)
    logger.info("Testing model swap (RAFT → SigLIP)...")
    start = time.perf_counter()
    try:
        mm.load_siglip()
        elapsed = time.perf_counter() - start
        perf_metrics.record("model_swap_raft_to_siglip", elapsed)
        logger.info(f"Model swap completed in {elapsed:.3f}s")
    except Exception as e:
        logger.warning(f"Model swap failed: {e}")

    # Cleanup
    mm.unload()
    gc.collect()


# ══════════════════════════════════════════════════════════════
# Test 2: Video Analysis Performance
# ══════════════════════════════════════════════════════════════


def test_scene_detection_performance(perf_metrics, tmp_path):
    """Profile PySceneDetect scene detection."""
    try:
        from services.video_analysis_service import detect_scenes
    except ImportError:
        pytest.skip("VideoAnalysisService not available")

    # Create test video
    test_video = tmp_path / "test_video.mp4"
    if not _create_test_video(str(test_video), duration=10.0):
        pytest.skip("FFmpeg not available for test video creation")

    logger.info("Testing scene detection (10s video)...")
    start = time.perf_counter()
    scenes = detect_scenes(str(test_video), threshold=27.0, min_scene_len=1.0)
    elapsed = time.perf_counter() - start

    perf_metrics.record(
        "scene_detection_10s_video",
        elapsed,
        {"num_scenes": len(scenes), "video_duration": 10.0},
    )
    logger.info(f"Detected {len(scenes)} scenes in {elapsed:.3f}s")


def test_raft_motion_performance(perf_metrics, tmp_path):
    """Profile RAFT optical flow motion scoring."""
    try:
        from services.video_analysis_service import detect_scenes, _load_raft_model, _raft_motion_score
        import cv2
        import numpy as np
    except ImportError:
        pytest.skip("RAFT or OpenCV not available")

    # Create test video
    test_video = tmp_path / "test_video.mp4"
    if not _create_test_video(str(test_video), duration=5.0):
        pytest.skip("FFmpeg not available")

    # Load RAFT
    logger.info("Loading RAFT model...")
    raft_model, device = _load_raft_model()
    if raft_model is None:
        pytest.skip("RAFT model not available")

    # Extract two frames
    cap = cv2.VideoCapture(str(test_video))
    ret1, frame1 = cap.read()
    cap.set(cv2.CAP_PROP_POS_FRAMES, 15)  # Skip ahead
    ret2, frame2 = cap.read()
    cap.release()

    if not (ret1 and ret2):
        pytest.skip("Failed to extract frames")

    logger.info("Testing RAFT motion score calculation...")
    start = time.perf_counter()
    score = _raft_motion_score(raft_model, device, frame1, frame2)
    elapsed = time.perf_counter() - start

    perf_metrics.record(
        "raft_motion_score_single",
        elapsed,
        {"score": f"{score:.4f}", "device": str(device)},
    )
    logger.info(f"RAFT motion score: {score:.4f} in {elapsed:.3f}s")


def test_siglip_embedding_performance(perf_metrics, tmp_path):
    """Profile SigLIP embedding generation."""
    try:
        from services.model_manager import ModelManager
        import cv2
        import numpy as np
        import torch
    except ImportError:
        pytest.skip("SigLIP dependencies not available")

    mm = ModelManager()

    # Load SigLIP
    logger.info("Loading SigLIP model...")
    try:
        mm.load_siglip()
    except Exception as e:
        pytest.skip(f"SigLIP not available: {e}")

    # Create test image
    test_img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

    logger.info("Testing SigLIP embedding generation (single frame)...")
    start = time.perf_counter()
    try:
        # This is a simplified test - actual implementation may differ
        # based on how SigLIP is wrapped in model_manager.py
        embedding = mm.encode_image(test_img)
        elapsed = time.perf_counter() - start
        perf_metrics.record(
            "siglip_embedding_single",
            elapsed,
            {"embedding_dim": len(embedding) if hasattr(embedding, "__len__") else "N/A"},
        )
        logger.info(f"SigLIP embedding generated in {elapsed:.3f}s")
    except AttributeError:
        logger.warning("SigLIP encode_image method not found - skipping")

    mm.unload()


# ══════════════════════════════════════════════════════════════
# Test 3: Audio Analysis Performance
# ══════════════════════════════════════════════════════════════


def test_beat_detection_performance(perf_metrics, tmp_path):
    """Profile GPU-accelerated beat detection."""
    try:
        from services.beat_analysis_service import analyze_audio
    except ImportError:
        pytest.skip("BeatAnalysisService not available")

    # Create test audio
    test_audio = tmp_path / "test_audio.wav"
    if not _create_test_audio(str(test_audio), duration=30.0, bpm=120):
        pytest.skip("Failed to create test audio")

    logger.info("Testing beat detection (30s audio, 120 BPM)...")
    start = time.perf_counter()
    try:
        result = analyze_audio(str(test_audio), use_gpu=True)
        elapsed = time.perf_counter() - start
        perf_metrics.record(
            "beat_detection_30s_audio",
            elapsed,
            {
                "num_beats": len(result.get("beats", [])),
                "bpm": result.get("bpm", "N/A"),
            },
        )
        logger.info(f"Beat detection completed in {elapsed:.3f}s")
    except Exception as e:
        logger.warning(f"Beat detection failed: {e}")


def test_demucs_stem_separation_performance(perf_metrics, tmp_path):
    """Profile Demucs 4-stem separation."""
    try:
        from services.ai_audio_service import separate_stems
    except ImportError:
        pytest.skip("AIAudioService not available")

    # Create test audio
    test_audio = tmp_path / "test_audio.wav"
    if not _create_test_audio(str(test_audio), duration=10.0, bpm=120):
        pytest.skip("Failed to create test audio")

    logger.info("Testing Demucs stem separation (10s audio)...")
    start = time.perf_counter()
    try:
        stems = separate_stems(str(test_audio))
        elapsed = time.perf_counter() - start
        perf_metrics.record(
            "demucs_stem_separation_10s",
            elapsed,
            {"num_stems": len(stems) if stems else 0},
        )
        logger.info(f"Stem separation completed in {elapsed:.3f}s")
    except Exception as e:
        logger.warning(f"Stem separation failed: {e}")


# ══════════════════════════════════════════════════════════════
# Test 4: Export Performance
# ══════════════════════════════════════════════════════════════


def test_ffmpeg_export_performance(perf_metrics, tmp_path):
    """Profile FFmpeg export with different codecs."""
    import subprocess

    # Create test video
    test_video = tmp_path / "test_source.mp4"
    if not _create_test_video(str(test_video), duration=10.0):
        pytest.skip("FFmpeg not available")

    # Test 1: Software encoding (libx264 ultrafast)
    logger.info("Testing FFmpeg export (libx264 ultrafast)...")
    output_libx264 = tmp_path / "output_libx264.mp4"
    start = time.perf_counter()
    _ffmpeg_export(str(test_video), str(output_libx264), "libx264", "ultrafast")
    elapsed = time.perf_counter() - start
    perf_metrics.record(
        "export_10s_libx264_ultrafast",
        elapsed,
        {"codec": "libx264", "preset": "ultrafast"},
    )
    logger.info(f"libx264 export completed in {elapsed:.3f}s")

    # Test 2: Hardware encoding (NVENC) if available
    logger.info("Testing FFmpeg export (h264_nvenc)...")
    output_nvenc = tmp_path / "output_nvenc.mp4"
    try:
        start = time.perf_counter()
        _ffmpeg_export(str(test_video), str(output_nvenc), "h264_nvenc", "fast")
        elapsed = time.perf_counter() - start
        perf_metrics.record(
            "export_10s_h264_nvenc_fast",
            elapsed,
            {"codec": "h264_nvenc", "preset": "fast"},
        )
        logger.info(f"NVENC export completed in {elapsed:.3f}s")
    except RuntimeError as e:
        logger.warning(f"NVENC not available: {e}")


# ══════════════════════════════════════════════════════════════
# Test 5: Memory/VRAM Profiling
# ══════════════════════════════════════════════════════════════


def test_vram_usage_profiling(perf_metrics):
    """Profile VRAM usage during model operations."""
    try:
        import torch
        from services.model_manager import ModelManager
    except ImportError:
        pytest.skip("torch not available")

    if not torch.cuda.is_available():
        pytest.skip("CUDA not available")

    mm = ModelManager()

    def get_vram_mb():
        return torch.cuda.memory_allocated() / 1024 / 1024

    logger.info("Profiling VRAM usage...")

    # Baseline
    vram_baseline = get_vram_mb()
    logger.info(f"VRAM baseline: {vram_baseline:.1f} MB")

    # Load SigLIP
    try:
        mm.load_siglip()
        vram_siglip = get_vram_mb()
        logger.info(f"VRAM with SigLIP: {vram_siglip:.1f} MB (+{vram_siglip - vram_baseline:.1f} MB)")
        perf_metrics.record("vram_siglip_mb", vram_siglip - vram_baseline)
    except Exception as e:
        logger.warning(f"SigLIP VRAM test failed: {e}")

    # Unload
    mm.unload()
    torch.cuda.empty_cache()
    gc.collect()
    vram_after_unload = get_vram_mb()
    logger.info(f"VRAM after unload: {vram_after_unload:.1f} MB")

    # Load RAFT
    try:
        mm.load_raft()
        vram_raft = get_vram_mb()
        logger.info(f"VRAM with RAFT: {vram_raft:.1f} MB (+{vram_raft - vram_baseline:.1f} MB)")
        perf_metrics.record("vram_raft_mb", vram_raft - vram_baseline)
    except Exception as e:
        logger.warning(f"RAFT VRAM test failed: {e}")

    mm.unload()


# ══════════════════════════════════════════════════════════════
# Helper Functions
# ══════════════════════════════════════════════════════════════


def _create_test_audio(path: str, duration: float = 5.0, bpm: int = 120, sr: int = 44100) -> bool:
    """Create synthetic WAV file with beat pattern."""
    try:
        import numpy as np
        import wave

        t = np.linspace(0, duration, int(sr * duration), endpoint=False)

        # 440 Hz sine + kick pattern at BPM
        beat_interval = 60.0 / bpm
        kick = np.zeros_like(t)
        for beat_time in np.arange(0, duration, beat_interval):
            mask = (t >= beat_time) & (t < beat_time + 0.05)
            kick[mask] = 0.8 * np.sin(2 * np.pi * 60 * (t[mask] - beat_time))

        signal = 0.3 * np.sin(2 * np.pi * 440 * t) + kick
        signal = np.clip(signal, -1.0, 1.0)
        samples = (signal * 32767).astype(np.int16)

        with wave.open(path, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(samples.tobytes())

        return True
    except Exception as e:
        logger.error(f"Failed to create test audio: {e}")
        return False


def _create_test_video(path: str, duration: float = 5.0, fps: int = 30, width: int = 640, height: int = 480) -> bool:
    """Create test MP4 with FFmpeg."""
    import subprocess

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=duration={duration}:size={width}x{height}:rate={fps}",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "28",
        "-pix_fmt",
        "yuv420p",
        "-v",
        "quiet",
        path,
    ]

    try:
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(cmd, capture_output=True, timeout=30, **kwargs)
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Failed to create test video: {e}")
        return False


def _ffmpeg_export(input_path: str, output_path: str, codec: str, preset: str):
    """Run FFmpeg export."""
    import subprocess

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-c:v",
        codec,
        "-preset",
        preset,
        "-v",
        "quiet",
        output_path,
    ]

    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    result = subprocess.run(cmd, capture_output=True, timeout=60, **kwargs)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg export failed: {result.stderr.decode()[:200]}")


# ══════════════════════════════════════════════════════════════
# Direct Run (without pytest)
# ══════════════════════════════════════════════════════════════


def run_profiling_suite():
    """Run all profiling tests directly (no pytest)."""
    import tempfile

    metrics = PerformanceMetrics()
    tmp_path = Path(tempfile.mkdtemp(prefix="pb_perf_"))

    print("\n" + "=" * 80)
    print("Starting PB Studio Performance Profiling...")
    print("=" * 80 + "\n")

    # Run each test
    try:
        test_model_loading_performance(metrics)
    except Exception as e:
        logger.error(f"Model loading test failed: {e}")

    try:
        test_scene_detection_performance(metrics, tmp_path)
    except Exception as e:
        logger.error(f"Scene detection test failed: {e}")

    try:
        test_beat_detection_performance(metrics, tmp_path)
    except Exception as e:
        logger.error(f"Beat detection test failed: {e}")

    try:
        test_ffmpeg_export_performance(metrics, tmp_path)
    except Exception as e:
        logger.error(f"FFmpeg export test failed: {e}")

    try:
        test_vram_usage_profiling(metrics)
    except Exception as e:
        logger.error(f"VRAM profiling test failed: {e}")

    # Report
    metrics.report()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--pytest":
        # Run via pytest
        pytest.main([__file__, "-v", "-s"])
    else:
        # Direct run
        run_profiling_suite()
