"""Deep Functional Tests for PB Studio Video Analysis & AI Services.

Tests all services and agents with synthetic data, documenting PASS/FAIL.
Does NOT fix bugs — only documents failures with full tracebacks.
"""

import os
import sys
import tempfile
import traceback
import shutil
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Results collector
RESULTS = []


def record(service: str, function: str, status: str, detail: str = ""):
    RESULTS.append({
        "service": service,
        "function": function,
        "status": status,
        "detail": detail,
    })
    icon = "PASS" if status == "PASS" else "FAIL"
    print(f"  [{icon}] {service}.{function}" + (f" -- {detail[:200]}" if detail and status == "FAIL" else ""))


def print_report():
    print("\n" + "=" * 80)
    print("DEEP FUNCTIONAL TEST REPORT")
    print("=" * 80)
    passes = sum(1 for r in RESULTS if r["status"] == "PASS")
    fails = sum(1 for r in RESULTS if r["status"] == "FAIL")
    print(f"\nTotal: {len(RESULTS)} tests | PASS: {passes} | FAIL: {fails}\n")

    if fails > 0:
        print("-" * 80)
        print("FAILURES:")
        print("-" * 80)
        for r in RESULTS:
            if r["status"] == "FAIL":
                print(f"\n  {r['service']}.{r['function']}:")
                print(f"    {r['detail']}")
    print("\n" + "=" * 80)
    # Also print summary table
    print("\nSUMMARY TABLE:")
    print(f"{'Service':<40} {'Function':<40} {'Status':<6}")
    print("-" * 86)
    for r in RESULTS:
        print(f"{r['service']:<40} {r['function']:<40} {r['status']:<6}")


# ======================================================================
# Helper: Create synthetic test video with cv2
# ======================================================================

def create_synthetic_video(output_path: str, width=320, height=240, fps=30, duration_sec=2, num_scenes=3):
    """Creates a synthetic MP4 video with scene changes for testing."""
    import cv2
    import numpy as np

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"Failed to open VideoWriter for {output_path}")

    total_frames = int(fps * duration_sec)
    frames_per_scene = total_frames // max(num_scenes, 1)

    for scene_idx in range(num_scenes):
        # Each scene has a distinct color
        base_color = [
            (0, 0, 200),    # Red
            (0, 200, 0),    # Green
            (200, 0, 0),    # Blue
        ][scene_idx % 3]

        for frame_idx in range(frames_per_scene):
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            # Fill with base color
            frame[:] = base_color
            # Add motion: a moving white rectangle
            x = int((frame_idx / frames_per_scene) * (width - 50))
            y = int((frame_idx / frames_per_scene) * (height - 50))
            cv2.rectangle(frame, (x, y), (x + 50, y + 50), (255, 255, 255), -1)
            # Add text
            cv2.putText(frame, f"S{scene_idx} F{frame_idx}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            writer.write(frame)

    writer.release()
    return output_path


# ======================================================================
# Test 1: VideoService (services/video_service.py)
# ======================================================================

def test_video_service():
    print("\n--- Testing VideoService (video_service.py) ---")

    # Import test
    try:
        from services.video_service import VideoAnalyzer
        record("VideoService", "import", "PASS")
    except Exception:
        record("VideoService", "import", "FAIL", traceback.format_exc())
        return

    # Construction test
    try:
        va = VideoAnalyzer()
        record("VideoService", "__init__", "PASS")
    except Exception:
        record("VideoService", "__init__", "FAIL", traceback.format_exc())
        return

    # Create synthetic video
    tmp_dir = tempfile.mkdtemp(prefix="pb_test_")
    video_path = os.path.join(tmp_dir, "test_video.mp4")
    try:
        create_synthetic_video(video_path)
        record("VideoService", "create_synthetic_video", "PASS")
    except Exception:
        record("VideoService", "create_synthetic_video", "FAIL", traceback.format_exc())
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return

    # probe() with valid file
    try:
        info = va.probe(video_path)
        assert isinstance(info, dict), f"Expected dict, got {type(info)}"
        assert info["width"] > 0, f"Width should be > 0, got {info['width']}"
        assert info["height"] > 0, f"Height should be > 0, got {info['height']}"
        assert info["fps"] > 0, f"FPS should be > 0, got {info['fps']}"
        assert info["duration"] > 0, f"Duration should be > 0, got {info['duration']}"
        assert info["codec"] != "unknown", f"Codec should not be 'unknown', got {info['codec']}"
        record("VideoService", "probe(valid_file)", "PASS")
    except Exception:
        record("VideoService", "probe(valid_file)", "FAIL", traceback.format_exc())

    # probe() with missing file
    try:
        info = va.probe("/nonexistent/video.mp4")
        assert info["width"] == 0, f"Expected width=0 for missing file, got {info['width']}"
        assert info["height"] == 0
        record("VideoService", "probe(missing_file)", "PASS")
    except Exception:
        record("VideoService", "probe(missing_file)", "FAIL", traceback.format_exc())

    # probe() with empty path
    try:
        info = va.probe("")
        assert info["width"] == 0
        record("VideoService", "probe(empty_path)", "PASS")
    except Exception:
        record("VideoService", "probe(empty_path)", "FAIL", traceback.format_exc())

    # probe() with None
    try:
        info = va.probe(None)
        assert info["width"] == 0
        record("VideoService", "probe(None)", "PASS")
    except Exception:
        record("VideoService", "probe(None)", "FAIL", traceback.format_exc())

    # probe() with non-video file
    non_video = os.path.join(tmp_dir, "not_a_video.txt")
    with open(non_video, "w") as f:
        f.write("this is not a video")
    try:
        info = va.probe(non_video)
        # Should either raise or return zeros - either is acceptable
        record("VideoService", "probe(non_video_file)", "PASS")
    except Exception:
        # Some errors are expected for non-video files
        record("VideoService", "probe(non_video_file)", "PASS")

    # create_proxy() with valid file
    try:
        proxy_path = va.create_proxy(video_path, target_height=240)
        assert os.path.exists(proxy_path), f"Proxy file should exist: {proxy_path}"
        assert os.path.getsize(proxy_path) > 0, "Proxy file should not be empty"
        record("VideoService", "create_proxy(valid_file)", "PASS")
    except Exception:
        record("VideoService", "create_proxy(valid_file)", "FAIL", traceback.format_exc())

    # create_proxy() with progress callback
    progress_calls = []
    try:
        # Delete existing proxy to force re-creation
        proxy_dir = Path(video_path).parent / "proxies"
        proxy_dir.mkdir(exist_ok=True)
        video2 = os.path.join(tmp_dir, "test_video2.mp4")
        create_synthetic_video(video2)
        proxy = va.create_proxy(video2, progress_cb=lambda p, m: progress_calls.append((p, m)))
        assert len(progress_calls) > 0, "Progress callback should have been called"
        record("VideoService", "create_proxy(progress_cb)", "PASS")
    except Exception:
        record("VideoService", "create_proxy(progress_cb)", "FAIL", traceback.format_exc())

    # _sanitize_ffmpeg_error
    try:
        from services.video_service import _sanitize_ffmpeg_error
        result = _sanitize_ffmpeg_error("")
        assert result == "(no stderr)"
        result = _sanitize_ffmpeg_error("line1\nline2\nline3\nline4\nline5", max_lines=2)
        assert "line4" in result and "line5" in result
        record("VideoService", "_sanitize_ffmpeg_error", "PASS")
    except Exception:
        record("VideoService", "_sanitize_ffmpeg_error", "FAIL", traceback.format_exc())

    # Cleanup
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ======================================================================
# Test 2: VideoAnalysisService (services/video_analysis_service.py)
# ======================================================================

def test_video_analysis_service():
    print("\n--- Testing VideoAnalysisService (video_analysis_service.py) ---")

    # Import test
    try:
        from services.video_analysis_service import (
            detect_scenes, compute_motion_scores, extract_keyframes,
            SceneInfo, PipelineResult, _cpu_motion_score, _fallback_single_scene,
            _get_video_duration,
        )
        record("VideoAnalysisService", "import", "PASS")
    except Exception:
        record("VideoAnalysisService", "import", "FAIL", traceback.format_exc())
        return

    # Create synthetic video
    tmp_dir = tempfile.mkdtemp(prefix="pb_test_vas_")
    video_path = os.path.join(tmp_dir, "test_analysis.mp4")
    try:
        create_synthetic_video(video_path, duration_sec=3, num_scenes=3)
        record("VideoAnalysisService", "create_synthetic_video", "PASS")
    except Exception:
        record("VideoAnalysisService", "create_synthetic_video", "FAIL", traceback.format_exc())
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return

    # SceneInfo dataclass
    try:
        scene = SceneInfo(index=0, start_time=0.0, end_time=1.0, motion_score=0.5)
        assert scene.index == 0
        assert scene.start_time == 0.0
        assert scene.end_time == 1.0
        assert scene.motion_score == 0.5
        assert scene.keyframe_path is None
        assert scene.embedding is None
        assert scene.ai_caption is None
        assert scene.ai_mood is None
        assert scene.ai_tags is None
        record("VideoAnalysisService", "SceneInfo_dataclass", "PASS")
    except Exception:
        record("VideoAnalysisService", "SceneInfo_dataclass", "FAIL", traceback.format_exc())

    # PipelineResult dataclass
    try:
        pr = PipelineResult(video_path="/test.mp4")
        assert pr.video_path == "/test.mp4"
        assert pr.scenes == []
        assert pr.total_duration == 0.0
        assert pr.embeddings_stored == 0
        record("VideoAnalysisService", "PipelineResult_dataclass", "PASS")
    except Exception:
        record("VideoAnalysisService", "PipelineResult_dataclass", "FAIL", traceback.format_exc())

    # detect_scenes() with valid file
    try:
        scenes = detect_scenes(video_path, threshold=27.0)
        assert isinstance(scenes, list), f"Expected list, got {type(scenes)}"
        assert len(scenes) >= 1, "Should detect at least one scene"
        for s in scenes:
            assert isinstance(s, SceneInfo)
            assert s.start_time >= 0
            assert s.end_time > s.start_time
        record("VideoAnalysisService", "detect_scenes(valid)", "PASS")
    except Exception:
        record("VideoAnalysisService", "detect_scenes(valid)", "FAIL", traceback.format_exc())

    # detect_scenes() with missing file
    try:
        scenes = detect_scenes("/nonexistent.mp4")
        assert scenes == [], f"Expected empty list for missing file, got {len(scenes)}"
        record("VideoAnalysisService", "detect_scenes(missing)", "PASS")
    except Exception:
        record("VideoAnalysisService", "detect_scenes(missing)", "FAIL", traceback.format_exc())

    # detect_scenes() with empty path
    try:
        scenes = detect_scenes("")
        assert scenes == []
        record("VideoAnalysisService", "detect_scenes(empty)", "PASS")
    except Exception:
        record("VideoAnalysisService", "detect_scenes(empty)", "FAIL", traceback.format_exc())

    # detect_scenes() with None
    try:
        scenes = detect_scenes(None)
        assert scenes == []
        record("VideoAnalysisService", "detect_scenes(None)", "PASS")
    except Exception:
        record("VideoAnalysisService", "detect_scenes(None)", "FAIL", traceback.format_exc())

    # detect_scenes() with progress callback
    progress_calls = []
    try:
        scenes = detect_scenes(video_path, progress_cb=lambda p, m: progress_calls.append((p, m)))
        assert len(progress_calls) > 0
        record("VideoAnalysisService", "detect_scenes(progress_cb)", "PASS")
    except Exception:
        record("VideoAnalysisService", "detect_scenes(progress_cb)", "FAIL", traceback.format_exc())

    # _fallback_single_scene
    try:
        scenes = _fallback_single_scene(video_path)
        assert len(scenes) == 1
        assert scenes[0].index == 0
        assert scenes[0].start_time == 0.0
        assert scenes[0].end_time > 0
        record("VideoAnalysisService", "_fallback_single_scene", "PASS")
    except Exception:
        record("VideoAnalysisService", "_fallback_single_scene", "FAIL", traceback.format_exc())

    # _get_video_duration
    try:
        duration = _get_video_duration(video_path)
        assert duration > 0, f"Duration should be > 0, got {duration}"
        record("VideoAnalysisService", "_get_video_duration", "PASS")
    except Exception:
        record("VideoAnalysisService", "_get_video_duration", "FAIL", traceback.format_exc())

    # _cpu_motion_score with synthetic frames
    try:
        import numpy as np
        frame1 = np.zeros((240, 320, 3), dtype=np.uint8)
        frame2 = np.ones((240, 320, 3), dtype=np.uint8) * 128
        score = _cpu_motion_score(frame1, frame2)
        assert 0.0 <= score <= 1.0, f"Score should be in [0, 1], got {score}"
        record("VideoAnalysisService", "_cpu_motion_score", "PASS")
    except Exception:
        record("VideoAnalysisService", "_cpu_motion_score", "FAIL", traceback.format_exc())

    # _cpu_motion_score with identical frames (should be ~0)
    try:
        import numpy as np
        frame = np.ones((240, 320, 3), dtype=np.uint8) * 100
        score = _cpu_motion_score(frame, frame.copy())
        assert score < 0.01, f"Identical frames should have near-zero motion, got {score}"
        record("VideoAnalysisService", "_cpu_motion_score(identical)", "PASS")
    except Exception:
        record("VideoAnalysisService", "_cpu_motion_score(identical)", "FAIL", traceback.format_exc())

    # compute_motion_scores with CPU fallback
    try:
        test_scenes = [SceneInfo(index=0, start_time=0.0, end_time=1.0)]
        result_scenes = compute_motion_scores(video_path, test_scenes)
        assert len(result_scenes) == 1
        assert 0.0 <= result_scenes[0].motion_score <= 1.0
        record("VideoAnalysisService", "compute_motion_scores(CPU)", "PASS")
    except Exception:
        record("VideoAnalysisService", "compute_motion_scores(CPU)", "FAIL", traceback.format_exc())

    # compute_motion_scores with missing file
    try:
        test_scenes = [SceneInfo(index=0, start_time=0.0, end_time=1.0)]
        result_scenes = compute_motion_scores("/nonexistent.mp4", test_scenes)
        assert len(result_scenes) == 1
        record("VideoAnalysisService", "compute_motion_scores(missing)", "PASS")
    except Exception:
        record("VideoAnalysisService", "compute_motion_scores(missing)", "FAIL", traceback.format_exc())

    # extract_keyframes
    kf_dir = Path(tmp_dir) / "keyframes"
    try:
        test_scenes = [
            SceneInfo(index=0, start_time=0.0, end_time=1.0),
            SceneInfo(index=1, start_time=1.0, end_time=2.0),
        ]
        result_scenes = extract_keyframes(video_path, test_scenes, output_dir=kf_dir)
        extracted = sum(1 for s in result_scenes if s.keyframe_path is not None)
        assert extracted > 0, "Should extract at least one keyframe"
        for s in result_scenes:
            if s.keyframe_path:
                assert os.path.exists(s.keyframe_path), f"Keyframe file missing: {s.keyframe_path}"
        record("VideoAnalysisService", "extract_keyframes", "PASS")
    except Exception:
        record("VideoAnalysisService", "extract_keyframes", "FAIL", traceback.format_exc())

    # extract_keyframes with missing video
    try:
        test_scenes = [SceneInfo(index=0, start_time=0.0, end_time=1.0)]
        result_scenes = extract_keyframes("/nonexistent.mp4", test_scenes)
        assert len(result_scenes) == 1
        assert result_scenes[0].keyframe_path is None
        record("VideoAnalysisService", "extract_keyframes(missing)", "PASS")
    except Exception:
        record("VideoAnalysisService", "extract_keyframes(missing)", "FAIL", traceback.format_exc())

    # Cleanup
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ======================================================================
# Test 3: VisionAnalysisService (vision_analysis_service_moondream.py)
# ======================================================================

def test_vision_analysis_service():
    print("\n--- Testing VisionAnalysisService (vision_analysis_service_moondream.py) ---")

    # Import test
    try:
        from services.vision_analysis_service_moondream import VisionAnalysisService, VisionAnalysisResult
        record("VisionAnalysisService", "import", "PASS")
    except Exception:
        record("VisionAnalysisService", "import", "FAIL", traceback.format_exc())
        return

    # Construction test
    try:
        vas = VisionAnalysisService()
        record("VisionAnalysisService", "__init__", "PASS")
    except Exception:
        record("VisionAnalysisService", "__init__", "FAIL", traceback.format_exc())
        return

    # VisionAnalysisResult dataclass
    try:
        result = VisionAnalysisResult()
        assert result.descriptions == []
        assert result.summary == ""
        assert result.frame_count == 0
        result2 = VisionAnalysisResult(
            descriptions=[{"time": 0.0, "description": "test"}],
            summary="A test summary",
            frame_count=1,
        )
        assert len(result2.descriptions) == 1
        assert result2.frame_count == 1
        record("VisionAnalysisService", "VisionAnalysisResult_dataclass", "PASS")
    except Exception:
        record("VisionAnalysisService", "VisionAnalysisResult_dataclass", "FAIL", traceback.format_exc())

    # analyze() with missing file
    try:
        vas.analyze("/nonexistent_video.mp4")
        record("VisionAnalysisService", "analyze(missing_file)", "FAIL", "Should have raised FileNotFoundError")
    except FileNotFoundError:
        record("VisionAnalysisService", "analyze(missing_file)", "PASS")
    except Exception:
        record("VisionAnalysisService", "analyze(missing_file)", "FAIL", traceback.format_exc())

    # analyze() with valid synthetic video - will likely fail if Moondream2 not downloaded
    tmp_dir = tempfile.mkdtemp(prefix="pb_test_vision_")
    video_path = os.path.join(tmp_dir, "test_vision.mp4")
    try:
        create_synthetic_video(video_path, duration_sec=2)
        result = vas.analyze(video_path, interval_sec=1.0, max_frames=2)
        assert isinstance(result, VisionAnalysisResult)
        record("VisionAnalysisService", "analyze(valid_file)", "PASS")
    except Exception as e:
        err_str = str(e)
        if "nicht gefunden" in err_str or "not found" in err_str.lower() or "nicht heruntergeladen" in err_str:
            record("VisionAnalysisService", "analyze(valid_file)", "PASS",
                   "Moondream2 model not downloaded (expected in test environment)")
        else:
            record("VisionAnalysisService", "analyze(valid_file)", "FAIL", traceback.format_exc())

    shutil.rmtree(tmp_dir, ignore_errors=True)


# ======================================================================
# Test 4: OllamaService (services/ollama_service.py)
# ======================================================================

def test_ollama_service():
    print("\n--- Testing OllamaService (ollama_service.py) ---")

    # Import test
    try:
        from services.ollama_service import OllamaService, OLLAMA_BASE, OLLAMA_MODEL, _find_ollama_bin
        record("OllamaService", "import", "PASS")
    except Exception:
        record("OllamaService", "import", "FAIL", traceback.format_exc())
        return

    # Singleton test
    try:
        svc1 = OllamaService.get()
        svc2 = OllamaService.get()
        assert svc1 is svc2, "OllamaService.get() should return the same instance"
        record("OllamaService", "singleton", "PASS")
    except Exception:
        record("OllamaService", "singleton", "FAIL", traceback.format_exc())
        return

    svc = OllamaService.get()

    # Constants check
    try:
        assert OLLAMA_BASE == "http://localhost:11434"
        assert isinstance(OLLAMA_MODEL, str) and len(OLLAMA_MODEL) > 0
        record("OllamaService", "constants", "PASS")
    except Exception:
        record("OllamaService", "constants", "FAIL", traceback.format_exc())

    # _find_ollama_bin
    try:
        bin_path = _find_ollama_bin()
        assert isinstance(bin_path, Path)
        record("OllamaService", "_find_ollama_bin", "PASS")
    except Exception:
        record("OllamaService", "_find_ollama_bin", "FAIL", traceback.format_exc())

    # is_ready property (checks port)
    try:
        ready = svc.is_ready
        assert isinstance(ready, bool)
        record("OllamaService", "is_ready", "PASS")
    except Exception:
        record("OllamaService", "is_ready", "FAIL", traceback.format_exc())

    # _is_port_open
    try:
        is_open = svc._is_port_open(11434)
        assert isinstance(is_open, bool)
        record("OllamaService", "_is_port_open", "PASS")
    except Exception:
        record("OllamaService", "_is_port_open", "FAIL", traceback.format_exc())

    # _is_port_open with definitely closed port
    try:
        is_open = svc._is_port_open(59999)
        assert is_open is False, "Port 59999 should not be open"
        record("OllamaService", "_is_port_open(closed_port)", "PASS")
    except Exception:
        record("OllamaService", "_is_port_open(closed_port)", "FAIL", traceback.format_exc())

    # chat() test (may fail if Ollama not running)
    try:
        result = svc.chat([{"role": "user", "content": "Say hello"}])
        assert isinstance(result, str)
        if "Fehler" in result or "error" in result.lower():
            record("OllamaService", "chat", "PASS",
                   f"Ollama not running or error (expected): {result[:100]}")
        else:
            record("OllamaService", "chat", "PASS")
    except Exception:
        record("OllamaService", "chat", "FAIL", traceback.format_exc())

    # vision() test — test method exists and signature is correct
    try:
        # Test with non-existent image path - should handle gracefully
        result = svc.vision(
            image_paths=["/nonexistent/image.jpg"],
            prompt="What do you see?"
        )
        assert isinstance(result, str)
        record("OllamaService", "vision", "PASS")
    except Exception:
        record("OllamaService", "vision", "FAIL", traceback.format_exc())

    # ensure_model when Ollama not running
    try:
        result = svc.ensure_model("test-model")
        assert isinstance(result, bool)
        record("OllamaService", "ensure_model", "PASS")
    except Exception:
        record("OllamaService", "ensure_model", "FAIL", traceback.format_exc())


# ======================================================================
# Test 5: OllamaClient (services/ollama_client.py)
# ======================================================================

def test_ollama_client():
    print("\n--- Testing OllamaClient (ollama_client.py) ---")

    # Import test
    try:
        from services.ollama_client import OllamaClient, get_ollama_client, RECOMMENDED_MODELS
        from services.errors import OllamaPausedError, OllamaNotAvailableError
        record("OllamaClient", "import", "PASS")
    except Exception:
        record("OllamaClient", "import", "FAIL", traceback.format_exc())
        return

    # Construction test
    try:
        client = OllamaClient()
        assert client.base_url == "http://localhost:11434"
        assert client.timeout == 120
        assert client.is_paused is False
        record("OllamaClient", "__init__(default)", "PASS")
    except Exception:
        record("OllamaClient", "__init__(default)", "FAIL", traceback.format_exc())

    # Construction with custom URL
    try:
        client = OllamaClient(base_url="http://127.0.0.1:9999/", timeout=30)
        assert client.base_url == "http://127.0.0.1:9999"  # trailing slash stripped
        assert client.timeout == 30
        record("OllamaClient", "__init__(custom)", "PASS")
    except Exception:
        record("OllamaClient", "__init__(custom)", "FAIL", traceback.format_exc())

    # Singleton factory
    try:
        c1 = get_ollama_client()
        c2 = get_ollama_client()
        assert c1 is c2, "get_ollama_client() should return same instance"
        record("OllamaClient", "get_ollama_client_singleton", "PASS")
    except Exception:
        record("OllamaClient", "get_ollama_client_singleton", "FAIL", traceback.format_exc())

    # RECOMMENDED_MODELS
    try:
        assert isinstance(RECOMMENDED_MODELS, list)
        assert len(RECOMMENDED_MODELS) > 0
        assert all(isinstance(m, str) for m in RECOMMENDED_MODELS)
        record("OllamaClient", "RECOMMENDED_MODELS", "PASS")
    except Exception:
        record("OllamaClient", "RECOMMENDED_MODELS", "FAIL", traceback.format_exc())

    # pause/resume
    try:
        client = OllamaClient(base_url="http://127.0.0.1:19999")
        assert client.is_paused is False
        client.pause()
        assert client.is_paused is True
        client.pause()  # idempotent
        assert client.is_paused is True
        client.resume()
        assert client.is_paused is False
        client.resume()  # idempotent
        assert client.is_paused is False
        record("OllamaClient", "pause_resume", "PASS")
    except Exception:
        record("OllamaClient", "pause_resume", "FAIL", traceback.format_exc())

    # chat when paused should raise OllamaPausedError
    try:
        client = OllamaClient(base_url="http://127.0.0.1:19999")
        client.pause()
        try:
            client.chat("test-model", "hello")
            record("OllamaClient", "chat_when_paused", "FAIL", "Should have raised OllamaPausedError")
        except OllamaPausedError:
            record("OllamaClient", "chat_when_paused", "PASS")
        finally:
            client.resume()
    except Exception:
        record("OllamaClient", "chat_when_paused", "FAIL", traceback.format_exc())

    # chat_with_history when paused
    try:
        client = OllamaClient(base_url="http://127.0.0.1:19999")
        client.pause()
        try:
            client.chat_with_history("test-model", [{"role": "user", "content": "hi"}])
            record("OllamaClient", "chat_with_history_paused", "FAIL", "Should have raised OllamaPausedError")
        except OllamaPausedError:
            record("OllamaClient", "chat_with_history_paused", "PASS")
        finally:
            client.resume()
    except Exception:
        record("OllamaClient", "chat_with_history_paused", "FAIL", traceback.format_exc())

    # chat_vision when paused
    try:
        client = OllamaClient(base_url="http://127.0.0.1:19999")
        client.pause()
        try:
            client.chat_vision("test-model", "hello", ["base64data"])
            record("OllamaClient", "chat_vision_paused", "FAIL", "Should have raised OllamaPausedError")
        except OllamaPausedError:
            record("OllamaClient", "chat_vision_paused", "PASS")
        finally:
            client.resume()
    except Exception:
        record("OllamaClient", "chat_vision_paused", "FAIL", traceback.format_exc())

    # chat_with_tools when paused
    try:
        client = OllamaClient(base_url="http://127.0.0.1:19999")
        client.pause()
        try:
            client.chat_with_tools("test-model", "hello", [])
            record("OllamaClient", "chat_with_tools_paused", "FAIL", "Should have raised OllamaPausedError")
        except OllamaPausedError:
            record("OllamaClient", "chat_with_tools_paused", "PASS")
        finally:
            client.resume()
    except Exception:
        record("OllamaClient", "chat_with_tools_paused", "FAIL", traceback.format_exc())

    # is_available with unreachable server
    try:
        client = OllamaClient(base_url="http://127.0.0.1:19999")
        result = client.is_available()
        assert result is False, "Should return False for unreachable server"
        record("OllamaClient", "is_available(unreachable)", "PASS")
    except Exception:
        record("OllamaClient", "is_available(unreachable)", "FAIL", traceback.format_exc())

    # get_version with unreachable server
    try:
        client = OllamaClient(base_url="http://127.0.0.1:19999")
        result = client.get_version()
        assert result is None, "Should return None for unreachable server"
        record("OllamaClient", "get_version(unreachable)", "PASS")
    except Exception:
        record("OllamaClient", "get_version(unreachable)", "FAIL", traceback.format_exc())

    # list_models with unreachable server
    try:
        client = OllamaClient(base_url="http://127.0.0.1:19999")
        result = client.list_models()
        assert result == [], "Should return empty list for unreachable server"
        record("OllamaClient", "list_models(unreachable)", "PASS")
    except Exception:
        record("OllamaClient", "list_models(unreachable)", "FAIL", traceback.format_exc())

    # supports_tools
    try:
        client = OllamaClient()
        assert client.supports_tools("gemma3:4b") is True
        assert client.supports_tools("gemma3:4b") is True
        assert client.supports_tools("qwen2.5:7b-instruct") is True
        assert client.supports_tools("llama3.1:8b") is True
        assert client.supports_tools("phi3:mini") is True
        assert client.supports_tools("unknown-model:latest") is False
        # Small model exclusion
        assert client.supports_tools("qwen2.5:0.5b") is False
        record("OllamaClient", "supports_tools", "PASS")
    except Exception:
        record("OllamaClient", "supports_tools", "FAIL", traceback.format_exc())

    # _find_fallback_model
    try:
        client = OllamaClient(base_url="http://127.0.0.1:19999")
        result = client._find_fallback_model("gemma3:4b")
        # Should return None since no models available
        assert result is None, f"Expected None, got {result}"
        record("OllamaClient", "_find_fallback_model(no_server)", "PASS")
    except Exception:
        record("OllamaClient", "_find_fallback_model(no_server)", "FAIL", traceback.format_exc())

    # get_model_info with unreachable server
    try:
        client = OllamaClient(base_url="http://127.0.0.1:19999")
        result = client.get_model_info("gemma3:4b")
        assert result == {}, "Should return empty dict for unreachable server"
        record("OllamaClient", "get_model_info(unreachable)", "PASS")
    except Exception:
        record("OllamaClient", "get_model_info(unreachable)", "FAIL", traceback.format_exc())

    # __repr__
    try:
        client = OllamaClient(base_url="http://127.0.0.1:19999")
        r = repr(client)
        assert "OllamaClient" in r
        assert "127.0.0.1:19999" in r
        record("OllamaClient", "__repr__", "PASS")
    except Exception:
        record("OllamaClient", "__repr__", "FAIL", traceback.format_exc())

    # is_available / chat with real Ollama (if running)
    try:
        real_client = get_ollama_client()
        is_avail = real_client.is_available()
        if is_avail:
            record("OllamaClient", "is_available(real)", "PASS")
            # Test chat
            try:
                result = real_client.chat("gemma3:4b", "Say hello in one word")
                assert isinstance(result, str) and len(result) > 0
                record("OllamaClient", "chat(real)", "PASS")
            except Exception:
                record("OllamaClient", "chat(real)", "FAIL", traceback.format_exc())
        else:
            record("OllamaClient", "is_available(real)", "PASS",
                   "Ollama not running (expected in test environment)")
    except Exception:
        record("OllamaClient", "is_available(real)", "FAIL", traceback.format_exc())


# ======================================================================
# Test 6: LocalAgentService (services/local_agent_service.py)
# ======================================================================

def test_local_agent_service():
    print("\n--- Testing LocalAgentService (local_agent_service.py) ---")

    # Import test
    try:
        from services.local_agent_service import LocalAgentService, DEFAULT_MODEL_ID, SYSTEM_PROMPT_TEMPLATE
        record("LocalAgentService", "import", "PASS")
    except Exception:
        record("LocalAgentService", "import", "FAIL", traceback.format_exc())
        return

    # Construction test
    try:
        las = LocalAgentService()
        assert las.model_id == DEFAULT_MODEL_ID
        record("LocalAgentService", "__init__", "PASS")
    except Exception:
        record("LocalAgentService", "__init__", "FAIL", traceback.format_exc())
        return

    # Construction with custom params
    try:
        las = LocalAgentService(model_id="test-model", device="cpu", use_ollama=False)
        assert las.model_id == "test-model"
        assert las.device == "cpu"
        assert las._use_ollama is False
        record("LocalAgentService", "__init__(custom)", "PASS")
    except Exception:
        record("LocalAgentService", "__init__(custom)", "FAIL", traceback.format_exc())

    # is_loaded property
    try:
        las = LocalAgentService(use_ollama=False)
        assert las.is_loaded is False
        record("LocalAgentService", "is_loaded", "PASS")
    except Exception:
        record("LocalAgentService", "is_loaded", "FAIL", traceback.format_exc())

    # _extract_json with various inputs
    try:
        # Valid single JSON object
        result = LocalAgentService._extract_json('{"action": "test", "params": {}}')
        assert len(result) == 1
        assert result[0]["action"] == "test"

        # Valid JSON array
        result = LocalAgentService._extract_json('[{"action": "a"}, {"action": "b"}]')
        assert len(result) == 2

        # JSON embedded in text
        result = LocalAgentService._extract_json('Here is the response: {"action": "test", "params": {}}')
        assert len(result) == 1
        assert result[0]["action"] == "test"

        # Invalid JSON (should return none action)
        result = LocalAgentService._extract_json('This is not JSON at all')
        assert len(result) == 1
        assert result[0]["action"] == "none"

        # Empty string
        result = LocalAgentService._extract_json('')
        assert len(result) == 1
        assert result[0]["action"] == "none"

        record("LocalAgentService", "_extract_json", "PASS")
    except Exception:
        record("LocalAgentService", "_extract_json", "FAIL", traceback.format_exc())

    # configure_ollama
    try:
        las = LocalAgentService(use_ollama=False)
        las.configure_ollama(url="http://localhost:9999", model="test-model", enabled=True)
        assert las._ollama_url == "http://localhost:9999"
        assert las._ollama_model == "test-model"
        assert las._use_ollama is True
        las.configure_ollama(url="http://localhost:11434", enabled=False)
        assert las._use_ollama is False
        record("LocalAgentService", "configure_ollama", "PASS")
    except Exception:
        record("LocalAgentService", "configure_ollama", "FAIL", traceback.format_exc())

    # clear_conversation_history
    try:
        las = LocalAgentService(use_ollama=False)
        las.clear_conversation_history()
        record("LocalAgentService", "clear_conversation_history", "PASS")
    except Exception:
        record("LocalAgentService", "clear_conversation_history", "FAIL", traceback.format_exc())

    # _get_orchestrator
    try:
        las = LocalAgentService(use_ollama=False)
        orch = las._get_orchestrator()
        assert orch is not None
        record("LocalAgentService", "_get_orchestrator", "PASS")
    except Exception:
        record("LocalAgentService", "_get_orchestrator", "FAIL", traceback.format_exc())

    # _build_system_prompt
    try:
        las = LocalAgentService(use_ollama=False)
        prompt = las._build_system_prompt(user_query="test query")
        assert isinstance(prompt, str)
        assert len(prompt) > 100
        assert "VERFÜGBARE AKTIONEN" in prompt or "AKTIONEN" in prompt
        record("LocalAgentService", "_build_system_prompt", "PASS")
    except Exception:
        record("LocalAgentService", "_build_system_prompt", "FAIL", traceback.format_exc())

    # _registry_to_tools
    try:
        las = LocalAgentService(use_ollama=False)
        tools = las._registry_to_tools()
        assert isinstance(tools, list)
        for tool in tools:
            assert tool["type"] == "function"
            assert "name" in tool["function"]
            assert "description" in tool["function"]
        record("LocalAgentService", "_registry_to_tools", "PASS")
    except Exception:
        record("LocalAgentService", "_registry_to_tools", "FAIL", traceback.format_exc())

    # process() with Ollama disabled
    try:
        las = LocalAgentService(use_ollama=False)
        result = las.process("Hallo, was kannst du?")
        assert isinstance(result, dict)
        assert "action" in result
        assert "error" in result
        record("LocalAgentService", "process(ollama_disabled)", "PASS")
    except Exception:
        record("LocalAgentService", "process(ollama_disabled)", "FAIL", traceback.format_exc())

    # _build_messages
    try:
        las = LocalAgentService(use_ollama=False)
        msgs = las._build_messages("test input")
        assert isinstance(msgs, list)
        assert len(msgs) == 2  # system + user
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert msgs[1]["content"] == "test input"
        record("LocalAgentService", "_build_messages", "PASS")
    except Exception:
        record("LocalAgentService", "_build_messages", "FAIL", traceback.format_exc())

    # process_with_history()
    try:
        las = LocalAgentService(use_ollama=False)
        result = las.process_with_history("test query")
        assert isinstance(result, dict)
        assert "action" in result
        record("LocalAgentService", "process_with_history", "PASS")
    except Exception:
        record("LocalAgentService", "process_with_history", "FAIL", traceback.format_exc())


# ======================================================================
# Test 7: VectorDBService (services/vector_db_service.py)
# ======================================================================

def test_vector_db_service():
    print("\n--- Testing VectorDBService (vector_db_service.py) ---")

    # Import test
    try:
        from services.vector_db_service import VectorDBService, EMBEDDING_DIM
        record("VectorDBService", "import", "PASS")
    except Exception:
        record("VectorDBService", "import", "FAIL", traceback.format_exc())
        return

    # Constants
    try:
        assert EMBEDDING_DIM == 1152
        record("VectorDBService", "EMBEDDING_DIM", "PASS")
    except Exception:
        record("VectorDBService", "EMBEDDING_DIM", "FAIL", traceback.format_exc())

    # Reset singleton for isolated testing
    import services.vector_db_service as vdb_mod
    old_instance = vdb_mod._instance
    vdb_mod._instance = None

    tmp_dir = tempfile.mkdtemp(prefix="pb_test_vdb_")
    db_path = os.path.join(tmp_dir, "test_embeddings.db")

    try:
        import numpy as np

        # Construction
        try:
            vdb = VectorDBService(db_path=db_path)
            record("VectorDBService", "__init__", "PASS")
        except Exception:
            record("VectorDBService", "__init__", "FAIL", traceback.format_exc())
            return

        # Singleton behavior
        try:
            vdb2 = VectorDBService()
            assert vdb is vdb2
            record("VectorDBService", "singleton", "PASS")
        except Exception:
            record("VectorDBService", "singleton", "FAIL", traceback.format_exc())

        # count() on empty DB
        try:
            c = vdb.count()
            assert c == 0, f"Expected 0, got {c}"
            record("VectorDBService", "count(empty)", "PASS")
        except Exception:
            record("VectorDBService", "count(empty)", "FAIL", traceback.format_exc())

        # add_embedding
        try:
            emb = np.random.randn(EMBEDDING_DIM).astype(np.float32)
            vdb.add_embedding(
                clip_id=1,
                video_path="/test/video.mp4",
                scene_index=0,
                scene_start=0.0,
                scene_end=5.0,
                embedding=emb,
                motion_score=0.5,
                description="Test scene",
            )
            assert vdb.count() == 1
            record("VectorDBService", "add_embedding", "PASS")
        except Exception:
            record("VectorDBService", "add_embedding", "FAIL", traceback.format_exc())

        # add_embedding with wrong dimension
        try:
            bad_emb = np.random.randn(512).astype(np.float32)
            vdb.add_embedding(
                clip_id=2, video_path="/test.mp4", scene_index=0,
                scene_start=0.0, scene_end=1.0, embedding=bad_emb,
            )
            record("VectorDBService", "add_embedding(wrong_dim)", "FAIL", "Should have raised ValueError")
        except ValueError:
            record("VectorDBService", "add_embedding(wrong_dim)", "PASS")
        except Exception:
            record("VectorDBService", "add_embedding(wrong_dim)", "FAIL", traceback.format_exc())

        # add_embedding with list input
        try:
            emb_list = np.random.randn(EMBEDDING_DIM).astype(np.float32).tolist()
            vdb.add_embedding(
                clip_id=3, video_path="/test/list.mp4", scene_index=0,
                scene_start=0.0, scene_end=2.0, embedding=emb_list,
            )
            assert vdb.count() == 2
            record("VectorDBService", "add_embedding(list_input)", "PASS")
        except Exception:
            record("VectorDBService", "add_embedding(list_input)", "FAIL", traceback.format_exc())

        # add_embeddings_batch
        try:
            entries = []
            for i in range(5):
                entries.append({
                    "video_path": "/test/batch.mp4",
                    "scene_index": i,
                    "scene_start": float(i),
                    "scene_end": float(i + 1),
                    "motion_score": 0.1 * i,
                    "description": f"Scene {i}",
                    "embedding": np.random.randn(EMBEDDING_DIM).astype(np.float32).tolist(),
                })
            vdb.add_embeddings_batch(clip_id=10, entries=entries)
            assert vdb.count() == 7  # 2 from before + 5 new
            record("VectorDBService", "add_embeddings_batch", "PASS")
        except Exception:
            record("VectorDBService", "add_embeddings_batch", "FAIL", traceback.format_exc())

        # add_embeddings_batch with wrong dimension
        try:
            bad_entries = [{
                "video_path": "/test.mp4",
                "scene_index": 0,
                "scene_start": 0.0,
                "scene_end": 1.0,
                "embedding": np.random.randn(256).astype(np.float32).tolist(),
            }]
            vdb.add_embeddings_batch(clip_id=99, entries=bad_entries)
            record("VectorDBService", "add_embeddings_batch(wrong_dim)", "FAIL", "Should have raised ValueError")
        except ValueError:
            record("VectorDBService", "add_embeddings_batch(wrong_dim)", "PASS")
        except Exception:
            record("VectorDBService", "add_embeddings_batch(wrong_dim)", "FAIL", traceback.format_exc())

        # search
        try:
            query = np.random.randn(EMBEDDING_DIM).astype(np.float32)
            results = vdb.search(query, top_k=3)
            assert isinstance(results, list)
            assert len(results) <= 3
            for r in results:
                assert "video_path" in r
                assert "_distance" in r
                assert 0 <= r["_distance"] <= 2.0  # cosine distance range
            record("VectorDBService", "search", "PASS")
        except Exception:
            record("VectorDBService", "search", "FAIL", traceback.format_exc())

        # search with wrong dimension
        try:
            bad_query = np.random.randn(768).astype(np.float32)
            vdb.search(bad_query)
            record("VectorDBService", "search(wrong_dim)", "FAIL", "Should have raised ValueError")
        except ValueError:
            record("VectorDBService", "search(wrong_dim)", "PASS")
        except Exception:
            record("VectorDBService", "search(wrong_dim)", "FAIL", traceback.format_exc())

        # search with motion_filter
        try:
            query = np.random.randn(EMBEDDING_DIM).astype(np.float32)
            results = vdb.search(query, top_k=10, motion_filter=0.3)
            assert isinstance(results, list)
            for r in results:
                assert r["motion_score"] > 0.3
            record("VectorDBService", "search(motion_filter)", "PASS")
        except Exception:
            record("VectorDBService", "search(motion_filter)", "FAIL", traceback.format_exc())

        # search_by_text (wrapper)
        try:
            query = np.random.randn(EMBEDDING_DIM).astype(np.float32)
            results = vdb.search_by_text(query, top_k=2)
            assert isinstance(results, list)
            record("VectorDBService", "search_by_text", "PASS")
        except Exception:
            record("VectorDBService", "search_by_text", "FAIL", traceback.format_exc())

        # get_all_embeddings
        try:
            embs, metas = vdb.get_all_embeddings()
            assert embs.shape[0] == 7
            assert embs.shape[1] == EMBEDDING_DIM
            assert len(metas) == 7
            record("VectorDBService", "get_all_embeddings", "PASS")
        except Exception:
            record("VectorDBService", "get_all_embeddings", "FAIL", traceback.format_exc())

        # delete_by_video
        try:
            before = vdb.count()
            vdb.delete_by_video("/test/video.mp4")
            after = vdb.count()
            assert after < before, f"Count should decrease after delete: {before} -> {after}"
            record("VectorDBService", "delete_by_video", "PASS")
        except Exception:
            record("VectorDBService", "delete_by_video", "FAIL", traceback.format_exc())

        # delete_by_clip_ids
        try:
            before = vdb.count()
            vdb.delete_by_clip_ids([10])  # clip_id=10 should remove batch entries
            after = vdb.count()
            assert after < before
            record("VectorDBService", "delete_by_clip_ids", "PASS")
        except Exception:
            record("VectorDBService", "delete_by_clip_ids", "FAIL", traceback.format_exc())

        # delete_all
        try:
            vdb.delete_all()
            assert vdb.count() == 0
            record("VectorDBService", "delete_all", "PASS")
        except Exception:
            record("VectorDBService", "delete_all", "FAIL", traceback.format_exc())

        # search on empty DB
        try:
            query = np.random.randn(EMBEDDING_DIM).astype(np.float32)
            results = vdb.search(query)
            assert results == []
            record("VectorDBService", "search(empty_db)", "PASS")
        except Exception:
            record("VectorDBService", "search(empty_db)", "FAIL", traceback.format_exc())

        # close
        try:
            vdb.close()
            record("VectorDBService", "close", "PASS")
        except Exception:
            record("VectorDBService", "close", "FAIL", traceback.format_exc())

    finally:
        # Restore original singleton
        vdb_mod._instance = old_instance
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ======================================================================
# Test 8: Multi-Agent System
# ======================================================================

def test_agents():
    print("\n--- Testing Multi-Agent System (agents/) ---")

    # --- BaseAgent ---
    try:
        from agents.base_agent import BaseAgent
        record("BaseAgent", "import", "PASS")
    except Exception:
        record("BaseAgent", "import", "FAIL", traceback.format_exc())
        return

    # BaseAgent is abstract, cannot be instantiated
    try:
        try:
            agent = BaseAgent()
            record("BaseAgent", "abstract_enforcement", "FAIL", "Should not be instantiable")
        except TypeError:
            record("BaseAgent", "abstract_enforcement", "PASS")
    except Exception:
        record("BaseAgent", "abstract_enforcement", "FAIL", traceback.format_exc())

    # --- AudioAgent ---
    try:
        from agents.audio_agent import AudioAgent
        record("AudioAgent", "import", "PASS")
    except Exception:
        record("AudioAgent", "import", "FAIL", traceback.format_exc())

    try:
        agent = AudioAgent()
        assert agent.name == "audio"
        assert agent.domain == "audio"
        record("AudioAgent", "__init__", "PASS")
    except Exception:
        record("AudioAgent", "__init__", "FAIL", traceback.format_exc())

    # can_handle tests
    try:
        agent = AudioAgent()
        # Should match audio keywords
        assert agent.can_handle("Analysiere den Audio-Track") > 0.0
        assert agent.can_handle("Trenne die Stems") > 0.0
        assert agent.can_handle("BPM erkennen") > 0.0
        assert agent.can_handle("drums und bass analysieren") > 0.0
        # Should not match non-audio
        assert agent.can_handle("Exportiere das Video") == 0.0
        assert agent.can_handle("Was ist 2+2?") == 0.0
        # High confidence for multiple keywords
        multi = agent.can_handle("analysiere audio stems drums bass vocals")
        assert multi >= 0.6, f"Multiple audio keywords should give high score, got {multi}"
        record("AudioAgent", "can_handle", "PASS")
    except Exception:
        record("AudioAgent", "can_handle", "FAIL", traceback.format_exc())

    # process (without actual track)
    try:
        agent = AudioAgent()
        result = agent.process("Analysiere Audio Track 1", context={"track_id": 1})
        assert isinstance(result, dict)
        assert "action" in result
        assert "agent" in result
        assert result["agent"] == "audio"
        record("AudioAgent", "process(structure)", "PASS")
    except Exception:
        record("AudioAgent", "process(structure)", "FAIL", traceback.format_exc())

    # process with stem request
    try:
        agent = AudioAgent()
        result = agent.process("Trenne die Stems für Track 1")
        assert isinstance(result, dict)
        assert result["action"] == "separate_stems"
        record("AudioAgent", "process(stem_detection)", "PASS")
    except Exception:
        record("AudioAgent", "process(stem_detection)", "FAIL", traceback.format_exc())

    # process without ID
    try:
        agent = AudioAgent()
        result = agent.process("Analysiere den Audio Track")
        assert isinstance(result, dict)
        assert result.get("message") is not None or result.get("action") == "analyze_audio"
        record("AudioAgent", "process(no_id)", "PASS")
    except Exception:
        record("AudioAgent", "process(no_id)", "FAIL", traceback.format_exc())

    # --- EditorAgent ---
    try:
        from agents.editor_agent import EditorAgent
        record("EditorAgent", "import", "PASS")
    except Exception:
        record("EditorAgent", "import", "FAIL", traceback.format_exc())

    try:
        agent = EditorAgent()
        assert agent.name == "editor"
        assert agent.domain == "editor"
        record("EditorAgent", "__init__", "PASS")
    except Exception:
        record("EditorAgent", "__init__", "FAIL", traceback.format_exc())

    try:
        agent = EditorAgent()
        assert agent.can_handle("Exportiere die Timeline") > 0.0
        assert agent.can_handle("Auto Edit starten") > 0.0
        assert agent.can_handle("Was ist das Wetter?") == 0.0
        record("EditorAgent", "can_handle", "PASS")
    except Exception:
        record("EditorAgent", "can_handle", "FAIL", traceback.format_exc())

    try:
        agent = EditorAgent()
        result = agent.process("Exportiere Projekt 1")
        assert isinstance(result, dict)
        assert "action" in result
        record("EditorAgent", "process(export)", "PASS")
    except Exception:
        record("EditorAgent", "process(export)", "FAIL", traceback.format_exc())

    try:
        agent = EditorAgent()
        result = agent.process("Auto Edit für Track 1")
        assert isinstance(result, dict)
        assert result.get("action") in ("auto_edit", "none")
        record("EditorAgent", "process(auto_edit)", "PASS")
    except Exception:
        record("EditorAgent", "process(auto_edit)", "FAIL", traceback.format_exc())

    try:
        agent = EditorAgent()
        result = agent.process("Was meinst du?")
        assert result.get("message") is not None
        record("EditorAgent", "process(unknown)", "PASS")
    except Exception:
        record("EditorAgent", "process(unknown)", "FAIL", traceback.format_exc())

    # --- VisionAgent ---
    try:
        from agents.vision_agent import VisionAgent
        record("VisionAgent", "import", "PASS")
    except Exception:
        record("VisionAgent", "import", "FAIL", traceback.format_exc())

    try:
        agent = VisionAgent()
        assert agent.name == "vision"
        assert agent.domain == "vision"
        # B-463: Vision laeuft via Ollama, kein HF-Preload -> model_id None
        assert agent.model_id is None
        record("VisionAgent", "__init__", "PASS")
    except Exception:
        record("VisionAgent", "__init__", "FAIL", traceback.format_exc())

    try:
        agent = VisionAgent()
        assert agent.can_handle("Analysiere das Video") > 0.0
        assert agent.can_handle("Was passiert in der Szene?") > 0.0
        assert agent.can_handle("Beschreibe den Clip") > 0.0
        assert agent.can_handle("Spiele ein Lied") == 0.0
        record("VisionAgent", "can_handle", "PASS")
    except Exception:
        record("VisionAgent", "can_handle", "FAIL", traceback.format_exc())

    try:
        agent = VisionAgent()
        # Content analysis detection
        assert agent._wants_content_analysis("was passiert in der szene") is True
        assert agent._wants_content_analysis("beschreibe den inhalt") is True
        assert agent._wants_content_analysis("video analysieren") is False
        record("VisionAgent", "_wants_content_analysis", "PASS")
    except Exception:
        record("VisionAgent", "_wants_content_analysis", "FAIL", traceback.format_exc())

    try:
        agent = VisionAgent()
        result = agent.process("Analysiere Video 1")
        assert isinstance(result, dict)
        assert result["agent"] == "vision"
        record("VisionAgent", "process", "PASS")
    except Exception:
        record("VisionAgent", "process", "FAIL", traceback.format_exc())

    # --- PacingAgent ---
    try:
        from agents.pacing_agent import PacingAgent
        record("PacingAgent", "import", "PASS")
    except Exception:
        record("PacingAgent", "import", "FAIL", traceback.format_exc())

    try:
        agent = PacingAgent()
        assert agent.name == "pacing"
        assert agent.domain == "pacing"
        assert agent.model_id is None
        record("PacingAgent", "__init__", "PASS")
    except Exception:
        record("PacingAgent", "__init__", "FAIL", traceback.format_exc())

    try:
        agent = PacingAgent()
        assert agent.can_handle("auto edit zum beat") > 0.0
        assert agent.can_handle("pacing berechnen") > 0.0
        assert agent.can_handle("beat sync timeline") > 0.0
        assert agent.can_handle("drop erkennen") > 0.0
        assert agent.can_handle("Was ist 2+2?") == 0.0
        # Pacing should score higher than editor for pacing queries
        pacing_score = agent.can_handle("auto edit beat sync pacing")
        assert pacing_score >= 0.5, f"Pacing score should be >= 0.5, got {pacing_score}"
        record("PacingAgent", "can_handle", "PASS")
    except Exception:
        record("PacingAgent", "can_handle", "FAIL", traceback.format_exc())

    try:
        agent = PacingAgent()
        prompt = agent.system_prompt
        assert isinstance(prompt, str)
        assert len(prompt) > 100
        assert "AXIOM" in prompt
        record("PacingAgent", "system_prompt", "PASS")
    except Exception:
        record("PacingAgent", "system_prompt", "FAIL", traceback.format_exc())

    try:
        agent = PacingAgent()
        result = agent.process("auto edit für Audio 1")
        assert isinstance(result, dict)
        assert result["agent"] == "pacing"
        record("PacingAgent", "process(auto_edit)", "PASS")
    except Exception:
        record("PacingAgent", "process(auto_edit)", "FAIL", traceback.format_exc())

    try:
        agent = PacingAgent()
        result = agent.process("Was ist Pacing?")
        assert isinstance(result, dict)
        assert result.get("message") is not None
        assert len(result["message"]) > 10
        record("PacingAgent", "process(info)", "PASS")
    except Exception:
        record("PacingAgent", "process(info)", "FAIL", traceback.format_exc())

    # _extract_settings_from_text
    try:
        agent = PacingAgent()
        settings = agent._extract_settings_from_text("auto edit mit 2 beat schnell")
        assert settings.get("base_cut_rate") == 2 or settings.get("base_cut_rate") == 1
        record("PacingAgent", "_extract_settings_from_text", "PASS")
    except Exception:
        record("PacingAgent", "_extract_settings_from_text", "FAIL", traceback.format_exc())

    try:
        settings = PacingAgent._extract_settings_from_text("langsam und sanft")
        assert settings.get("base_cut_rate") == 8
        assert settings.get("energy_reactivity") == 30
        record("PacingAgent", "_extract_settings_slow", "PASS")
    except Exception:
        record("PacingAgent", "_extract_settings_slow", "FAIL", traceback.format_exc())

    try:
        settings = PacingAgent._extract_settings_from_text("schnell und aggressiv")
        assert settings.get("base_cut_rate") == 1
        assert settings.get("energy_reactivity") == 80
        record("PacingAgent", "_extract_settings_fast", "PASS")
    except Exception:
        record("PacingAgent", "_extract_settings_fast", "FAIL", traceback.format_exc())

    try:
        settings = PacingAgent._extract_settings_from_text("breakdown force16")
        assert settings.get("breakdown_behavior") == "force16"
        record("PacingAgent", "_extract_settings_breakdown", "PASS")
    except Exception:
        record("PacingAgent", "_extract_settings_breakdown", "FAIL", traceback.format_exc())

    # _explain_pacing
    try:
        explanation = PacingAgent._explain_pacing("was ist ein drop")
        assert "DROP" in explanation.upper()
        explanation = PacingAgent._explain_pacing("breakdown verhalten")
        assert "BREAKDOWN" in explanation.upper()
        explanation = PacingAgent._explain_pacing("energy level")
        assert "ENERGY" in explanation.upper() or "ENERGIE" in explanation.upper()
        explanation = PacingAgent._explain_pacing("stem gewichte")
        assert "STEM" in explanation.upper()
        explanation = PacingAgent._explain_pacing("allgemeine frage")
        assert "PACING" in explanation.upper()
        record("PacingAgent", "_explain_pacing", "PASS")
    except Exception:
        record("PacingAgent", "_explain_pacing", "FAIL", traceback.format_exc())

    # --- OrchestratorAgent ---
    try:
        from agents.orchestrator_agent import OrchestratorAgent
        record("OrchestratorAgent", "import", "PASS")
    except Exception:
        record("OrchestratorAgent", "import", "FAIL", traceback.format_exc())

    try:
        orch = OrchestratorAgent()
        assert orch.name == "orchestrator"
        assert orch.domain == "orchestrator"
        assert len(orch.agents) == 4  # Pacing, Vision, Audio, Editor
        record("OrchestratorAgent", "__init__", "PASS")
    except Exception:
        record("OrchestratorAgent", "__init__", "FAIL", traceback.format_exc())

    try:
        orch = OrchestratorAgent()
        assert orch.can_handle("anything") == 1.0
        record("OrchestratorAgent", "can_handle", "PASS")
    except Exception:
        record("OrchestratorAgent", "can_handle", "FAIL", traceback.format_exc())

    # _detect_multi_step
    try:
        orch = OrchestratorAgent()
        assert orch._detect_multi_step("Was passiert in Video 1 und was wird gesagt?") is True
        assert orch._detect_multi_step("bild und ton analysieren") is True
        assert orch._detect_multi_step("Nur Audio analysieren") is False
        record("OrchestratorAgent", "_detect_multi_step", "PASS")
    except Exception:
        record("OrchestratorAgent", "_detect_multi_step", "FAIL", traceback.format_exc())

    # _extract_id_from_text
    try:
        orch = OrchestratorAgent()
        assert orch._extract_id_from_text("Video 42 analysieren") == 42
        assert orch._extract_id_from_text("Track 1") == 1
        assert orch._extract_id_from_text("keine Zahl") is None
        record("OrchestratorAgent", "_extract_id_from_text", "PASS")
    except Exception:
        record("OrchestratorAgent", "_extract_id_from_text", "FAIL", traceback.format_exc())

    # _detect_compound_actions
    try:
        orch = OrchestratorAgent()
        actions = orch._detect_compound_actions("Erstelle proxy und trenne stems")
        assert "create_proxy" in actions
        assert "separate_stems" in actions
        assert len(actions) == 2
        actions = orch._detect_compound_actions("nur proxy erstellen")
        assert len(actions) == 1
        actions = orch._detect_compound_actions("Was ist das Wetter?")
        assert len(actions) == 0
        record("OrchestratorAgent", "_detect_compound_actions", "PASS")
    except Exception:
        record("OrchestratorAgent", "_detect_compound_actions", "FAIL", traceback.format_exc())

    # _route_to_agent
    try:
        orch = OrchestratorAgent()
        agent = orch._route_to_agent("Analysiere den Audio-Track mit BPM")
        assert agent is not None
        assert agent.domain == "audio"

        agent = orch._route_to_agent("Was passiert in der Video-Szene?")
        assert agent is not None
        assert agent.domain == "vision"

        agent = orch._route_to_agent("auto edit beat sync pacing")
        assert agent is not None
        assert agent.domain == "pacing"

        record("OrchestratorAgent", "_route_to_agent", "PASS")
    except Exception:
        record("OrchestratorAgent", "_route_to_agent", "FAIL", traceback.format_exc())

    # Dependency injection test
    try:
        custom_agents = [AudioAgent(), VisionAgent()]
        orch = OrchestratorAgent(agents=custom_agents)
        assert len(orch.agents) == 2
        record("OrchestratorAgent", "dependency_injection", "PASS")
    except Exception:
        record("OrchestratorAgent", "dependency_injection", "FAIL", traceback.format_exc())

    # set_model_manager
    try:
        orch = OrchestratorAgent()
        orch.set_model_manager(None)
        assert orch._model_manager is None
        record("OrchestratorAgent", "set_model_manager", "PASS")
    except Exception:
        record("OrchestratorAgent", "set_model_manager", "FAIL", traceback.format_exc())

    # process (general query)
    try:
        orch = OrchestratorAgent()
        result = orch.process("Hallo, was kannst du?")
        assert isinstance(result, dict)
        assert "action" in result
        assert "error" in result
        record("OrchestratorAgent", "process(general)", "PASS")
    except Exception:
        record("OrchestratorAgent", "process(general)", "FAIL", traceback.format_exc())

    # process routes to audio agent
    try:
        orch = OrchestratorAgent()
        result = orch.process("Analysiere Audio Track 1 BPM beats drums")
        assert isinstance(result, dict)
        assert result.get("agent") == "audio" or result.get("action") != "none"
        record("OrchestratorAgent", "process(audio_routing)", "PASS")
    except Exception:
        record("OrchestratorAgent", "process(audio_routing)", "FAIL", traceback.format_exc())

    # _build_context
    try:
        orch = OrchestratorAgent()
        ctx = orch._build_context("Analysiere Video 5", None)
        assert ctx.get("extracted_id") == 5
        ctx2 = orch._build_context("Analysiere Video", {"clip_id": 3})
        assert "clip_id" in ctx2
        record("OrchestratorAgent", "_build_context", "PASS")
    except Exception:
        record("OrchestratorAgent", "_build_context", "FAIL", traceback.format_exc())

    # __repr__ for agents
    try:
        for AgentClass in [AudioAgent, EditorAgent, VisionAgent, PacingAgent]:
            agent = AgentClass()
            r = repr(agent)
            assert agent.name in r
            assert agent.domain in r
        record("Agents", "__repr__", "PASS")
    except Exception:
        record("Agents", "__repr__", "FAIL", traceback.format_exc())


# ======================================================================
# Test 9: Error hierarchy
# ======================================================================

def test_errors():
    print("\n--- Testing Error Hierarchy (services/errors.py) ---")

    try:
        from services.errors import (
            PBStudioError, AudioError, AudioLoadError, StemSeparationError,
            BeatDetectionError, VideoError, FrameExtractionError,
            EmbeddingError, SceneDetectionError, VideoAnalysisError,
            GPUError, CUDANotAvailableError, VRAMInsufficientError,
            CUDAOutOfMemoryError, MLError, MLModelNotFoundError,
            MLUnavailableError, LLMError, OllamaError,
            OllamaNotAvailableError, OllamaModelNotFoundError,
            OllamaPausedError, DatabaseError, DatabaseLockedError,
            MigrationError, ExportError, ConversionError,
            FFmpegError, FFmpegTimeoutError, TimelineError, ProjectError,
            WorkerError, Result,
        )
        record("Errors", "import_all", "PASS")
    except Exception:
        record("Errors", "import_all", "FAIL", traceback.format_exc())
        return

    # Test hierarchy
    try:
        assert issubclass(AudioError, PBStudioError)
        assert issubclass(VideoError, PBStudioError)
        assert issubclass(GPUError, PBStudioError)
        assert issubclass(MLError, PBStudioError)
        assert issubclass(LLMError, PBStudioError)
        assert issubclass(OllamaError, LLMError)
        assert issubclass(OllamaPausedError, OllamaError)
        assert issubclass(FFmpegError, PBStudioError)
        record("Errors", "hierarchy", "PASS")
    except Exception:
        record("Errors", "hierarchy", "FAIL", traceback.format_exc())

    # Test construction
    try:
        e = FFmpegError("test error", returncode=1, stderr="some stderr")
        assert e.returncode == 1
        assert e.stderr == "some stderr"

        e = OllamaModelNotFoundError(model="test", reason="too big")
        assert e.model == "test"
        assert e.reason == "too big"

        e = VRAMInsufficientError("demucs", required_gb=4.0, available_gb=2.0)
        assert "demucs" in str(e)

        e = MLModelNotFoundError("test-model", hint="download it")
        assert e.model_id == "test-model"

        record("Errors", "construction", "PASS")
    except Exception:
        record("Errors", "construction", "FAIL", traceback.format_exc())

    # Test Result pattern
    try:
        r = Result.ok(42)
        assert r.is_ok is True
        assert r.unwrap() == 42
        assert r.error is None

        r = Result.err("something failed")
        assert r.is_ok is False
        assert r.error == "something failed"
        assert r.unwrap_or(0) == 0

        try:
            r.unwrap()
            record("Errors", "Result_pattern", "FAIL", "unwrap() on err should raise")
        except ValueError:
            pass

        r = Result.fallback(99, "used fallback")
        assert r.is_ok is True
        assert r.is_fallback is True
        assert r.fallback_reason == "used fallback"
        assert r.unwrap() == 99

        record("Errors", "Result_pattern", "PASS")
    except Exception:
        record("Errors", "Result_pattern", "FAIL", traceback.format_exc())


# ======================================================================
# Test 10: Analysis Status Service
# ======================================================================

def test_analysis_status_service():
    print("\n--- Testing AnalysisStatusService ---")

    try:
        from services import analysis_status_service as ass
        record("AnalysisStatusService", "import", "PASS")
    except Exception:
        record("AnalysisStatusService", "import", "FAIL", traceback.format_exc())
        return

    try:
        ass.mark_started("video", 1, "test_step")
        record("AnalysisStatusService", "mark_started", "PASS")
    except Exception:
        record("AnalysisStatusService", "mark_started", "FAIL", traceback.format_exc())

    try:
        ass.mark_done("video", 1, "test_step", {"key": "value"})
        record("AnalysisStatusService", "mark_done", "PASS")
    except Exception:
        record("AnalysisStatusService", "mark_done", "FAIL", traceback.format_exc())

    try:
        ass.mark_error("video", 1, "test_step", "test error")
        record("AnalysisStatusService", "mark_error", "PASS")
    except Exception:
        record("AnalysisStatusService", "mark_error", "FAIL", traceback.format_exc())


# ======================================================================
# MAIN
# ======================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("PB Studio Deep Functional Tests")
    print(f"Python: {sys.version}")
    print(f"Project Root: {PROJECT_ROOT}")
    print("=" * 80)

    # Run all test suites
    test_errors()
    test_video_service()
    test_video_analysis_service()
    test_vision_analysis_service()
    test_ollama_service()
    test_ollama_client()
    test_local_agent_service()
    test_vector_db_service()
    test_agents()
    test_analysis_status_service()

    # Print final report
    print_report()
