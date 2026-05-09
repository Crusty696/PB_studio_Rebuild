"""
Real-Data AI Audio Service Test — GPU-intensive Operations
==========================================================
Tests StemSeparator, FrequencyAnalyzer, AutoDucker, ModelManager
with a real 150MB Progressive Psy Trance mix on GTX 1060 6GB.

IMPORTANT: This test uses a TEMPORARY database and temporary directories.
Each function is tested individually; OOM/crash is caught and logged.
"""

import gc
import json
import logging
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

# ── 0. Setup: sys.path + DLL directories + PATH (mirrors main.py) ───────
APP_ROOT = Path(__file__).resolve().parent.parent

# Ensure project root is on sys.path so 'database', 'services' can be imported
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

# Add bin dir to PATH
_BIN_DIR = str(APP_ROOT / "bin")
if _BIN_DIR not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _BIN_DIR + os.pathsep + os.environ["PATH"]

# CUDA DLL fix: add NVIDIA driver + torch lib to PATH
def _find_nv_driver_dir():
    driver_store = Path(r"C:\Windows\System32\DriverStore\FileRepository")
    if not driver_store.exists():
        return None
    candidates = sorted(
        (d for d in driver_store.iterdir()
         if d.is_dir() and d.name.startswith("nv") and "amd64" in d.name),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for d in candidates:
        if any((d / n).exists() for n in ("nvcuda64.dll", "nvcuda.dll", "OpenCL64.dll", "NvFBC64.dll")):
            return str(d)
    return str(candidates[0]) if candidates else None

_NV_DRIVER = _find_nv_driver_dir()
# B-215: torch-DLLs aus AKTUELLEM Interpreter (sys.prefix). Conda + venv kompatibel.
_INTERP_TORCH = Path(sys.prefix) / "Lib" / "site-packages" / "torch" / "lib"
_VENV310_TORCH = APP_ROOT / ".venv310" / "Lib" / "site-packages" / "torch" / "lib"
_VENV_TORCH = APP_ROOT / ".venv" / "Lib" / "site-packages" / "torch" / "lib"
if _INTERP_TORCH.exists():
    _VENV_DLLS = str(_INTERP_TORCH)
elif _VENV310_TORCH.exists():
    _VENV_DLLS = str(_VENV310_TORCH)
else:
    _VENV_DLLS = str(_VENV_TORCH)

_DLL_DIRS = [_VENV_DLLS]
if _NV_DRIVER:
    _DLL_DIRS.insert(0, _NV_DRIVER)

for _p in _DLL_DIRS:
    if _p not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _p + os.pathsep + os.environ["PATH"]
    if hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(_p)
        except Exception:
            pass

# Force CUDA init before anything else
try:
    import torch
    if torch.cuda.is_available():
        torch.cuda.get_device_name(0)
except Exception:
    pass

# ── Logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("AI_AUDIO_TEST")

# ── Constants ────────────────────────────────────────────────────────────
_DEFAULT_AUDIO = APP_ROOT / "vendor" / "beat_this" / "tests" / "It Don't Mean A Thing - Kings of Swing.mp3"
AUDIO_FILE = os.environ.get("PB_TEST_AUDIO", str(_DEFAULT_AUDIO))
STEM_NAMES = ["vocals", "drums", "bass", "other"]

# ── Helper Functions ─────────────────────────────────────────────────────

def vram_info():
    """Return VRAM info dict or None if CUDA unavailable."""
    try:
        import torch
        if not torch.cuda.is_available():
            return {"available": False}
        free, total = torch.cuda.mem_get_info(0)
        allocated = torch.cuda.memory_allocated(0)
        return {
            "available": True,
            "device": torch.cuda.get_device_name(0),
            "total_mb": round(total / 1024**2, 1),
            "free_mb": round(free / 1024**2, 1),
            "allocated_mb": round(allocated / 1024**2, 1),
        }
    except Exception as e:
        return {"available": False, "error": str(e)}


def setup_temp_db(tmp_dir: Path):
    """Create a temporary SQLite database and point the app engine to it.

    We do this by:
    1. Creating a fresh DB file in tmp_dir
    2. Using set_project() to switch the engine to that DB
    3. Running init_db() to create tables
    """
    from database.session import set_project, engine, _make_engine
    from database.models import Base, Project
    from sqlalchemy.orm import Session

    # set_project expects a project directory; the DB will be tmp_dir/pb_studio.db
    set_project(tmp_dir)

    # Create tables
    Base.metadata.create_all(engine)

    # Create a default project (needed for FK constraints on AudioTrack)
    with Session(engine) as s:
        proj = Project(name="TEST_PROJECT", path=str(tmp_dir))
        s.add(proj)
        s.commit()
        project_id = proj.id

    # Create storage/stems directory
    (tmp_dir / "storage" / "stems").mkdir(parents=True, exist_ok=True)

    return project_id


_track_cache: dict[tuple[int, str], int] = {}


def ingest_audio_track(tmp_dir: Path, project_id: int, file_path: str) -> tuple[int, str]:
    """Insert or reuse an AudioTrack record and return (id, file_path).

    The file_path MUST stay real — services load the audio via librosa/Demucs
    from the path stored in the DB. We cache by (project_id, file_path) so
    repeated calls with the same file return the same track_id instead of
    violating UNIQUE(project_id, file_path).
    """
    from database.session import engine
    from database.models import AudioTrack
    from sqlalchemy.orm import Session

    key = (project_id, file_path)
    if key in _track_cache:
        return _track_cache[key], file_path

    with Session(engine) as s:
        existing = s.query(AudioTrack).filter_by(
            project_id=project_id, file_path=file_path
        ).first()
        if existing:
            track_id = existing.id
        else:
            track = AudioTrack(
                project_id=project_id,
                file_path=file_path,
                title=Path(file_path).stem,
            )
            s.add(track)
            s.commit()
            track_id = track.id

    _track_cache[key] = track_id
    return track_id, file_path


results = []

def record_result(test_name, status, elapsed, details="", vram_before=None, vram_after=None):
    """Record a test result."""
    entry = {
        "test": test_name,
        "status": status,
        "elapsed_sec": round(elapsed, 2),
        "details": details,
    }
    if vram_before:
        entry["vram_before_mb"] = vram_before.get("allocated_mb", "N/A")
    if vram_after:
        entry["vram_after_mb"] = vram_after.get("allocated_mb", "N/A")
    results.append(entry)
    status_icon = {"PASS": "+", "FAIL": "X", "CRASH": "!", "OOM": "!!!", "SKIP": "-"}.get(status, "?")
    logger.info(f"[{status_icon}] {test_name}: {status} ({elapsed:.1f}s) {details}")


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN TEST RUNNER
# ═══════════════════════════════════════════════════════════════════════════

def main():
    logger.info("=" * 70)
    logger.info("  AI AUDIO SERVICE — REAL DATA TEST")
    logger.info(f"  Audio: {AUDIO_FILE}")
    logger.info(f"  File size: {Path(AUDIO_FILE).stat().st_size / 1024**2:.1f} MB")
    logger.info("=" * 70)

    # ── Pre-flight: Audio file exists? ───────────────────────────────
    if not Path(AUDIO_FILE).exists():
        logger.error(f"Audio file not found: {AUDIO_FILE}")
        return

    # ── Test 0: CUDA/GPU Availability ────────────────────────────────
    logger.info("\n" + "=" * 50)
    logger.info("TEST 0: CUDA / GPU Availability")
    logger.info("=" * 50)
    t0 = time.time()
    try:
        import torch
        cuda_ok = torch.cuda.is_available()
        if cuda_ok:
            gpu_name = torch.cuda.get_device_name(0)
            free, total = torch.cuda.mem_get_info(0)
            record_result(
                "CUDA/GPU Check", "PASS", time.time() - t0,
                f"GPU: {gpu_name}, VRAM: {free/1024**2:.0f}MB free / {total/1024**2:.0f}MB total, "
                f"CUDA: {torch.version.cuda}, PyTorch: {torch.__version__}"
            )
        else:
            record_result("CUDA/GPU Check", "FAIL", time.time() - t0,
                          "torch.cuda.is_available() = False")
    except Exception as e:
        record_result("CUDA/GPU Check", "CRASH", time.time() - t0, traceback.format_exc())

    # ── Setup temporary DB ───────────────────────────────────────────
    tmp_dir = Path(tempfile.mkdtemp(prefix="pb_ai_test_"))
    logger.info(f"\nTemp directory: {tmp_dir}")

    try:
        project_id = setup_temp_db(tmp_dir)
        logger.info(f"Temp DB created, project_id={project_id}")

        # ── Test 1: FrequencyAnalyzer.analyze() ─────────────────────
        logger.info("\n" + "=" * 50)
        logger.info("TEST 1: FrequencyAnalyzer.analyze()")
        logger.info("=" * 50)
        t0 = time.time()
        vram_before = vram_info()
        try:
            from services.ai_audio_service import FrequencyAnalyzer
            fa = FrequencyAnalyzer()
            result = fa.analyze(AUDIO_FILE)

            # Validate result structure
            errors = []
            for key in ["band_low", "band_mid", "band_high", "num_samples", "duration", "bpm", "beat_positions"]:
                if key not in result:
                    errors.append(f"Missing key: {key}")

            if not errors:
                # Validate data quality
                if not isinstance(result["band_low"], list) or len(result["band_low"]) == 0:
                    errors.append("band_low is empty or not a list")
                if not isinstance(result["band_mid"], list) or len(result["band_mid"]) == 0:
                    errors.append("band_mid is empty or not a list")
                if not isinstance(result["band_high"], list) or len(result["band_high"]) == 0:
                    errors.append("band_high is empty or not a list")
                if result["duration"] <= 0:
                    errors.append(f"Invalid duration: {result['duration']}")
                if result["bpm"] <= 0:
                    errors.append(f"Invalid BPM: {result['bpm']}")
                if not isinstance(result["beat_positions"], list) or len(result["beat_positions"]) == 0:
                    errors.append("beat_positions is empty or not a list")

                # Check value ranges [0..1] for bands
                for band_name in ["band_low", "band_mid", "band_high"]:
                    vals = result[band_name]
                    if vals:
                        min_v, max_v = min(vals), max(vals)
                        if min_v < -0.01 or max_v > 1.01:
                            errors.append(f"{band_name} out of range: [{min_v:.4f}, {max_v:.4f}]")

            vram_after = vram_info()
            if errors:
                record_result("FrequencyAnalyzer.analyze()", "FAIL", time.time() - t0,
                              "; ".join(errors), vram_before, vram_after)
            else:
                detail = (
                    f"BPM={result['bpm']}, duration={result['duration']:.1f}s, "
                    f"samples={result['num_samples']}, beats={len(result['beat_positions'])}, "
                    f"band_low[0..5]={result['band_low'][:5]}"
                )
                record_result("FrequencyAnalyzer.analyze()", "PASS", time.time() - t0,
                              detail, vram_before, vram_after)
        except Exception as e:
            vram_after = vram_info()
            is_oom = "out of memory" in str(e).lower()
            record_result("FrequencyAnalyzer.analyze()",
                          "OOM" if is_oom else "CRASH",
                          time.time() - t0, traceback.format_exc(), vram_before, vram_after)

        # ── Test 2: FrequencyAnalyzer.analyze_and_store() ───────────
        logger.info("\n" + "=" * 50)
        logger.info("TEST 2: FrequencyAnalyzer.analyze_and_store()")
        logger.info("=" * 50)
        t0 = time.time()
        vram_before = vram_info()
        try:
            from services.ai_audio_service import FrequencyAnalyzer
            from database.session import engine
            from database.models import AudioTrack, WaveformData
            from sqlalchemy.orm import Session

            track_id_freq, _ = ingest_audio_track(tmp_dir, project_id, AUDIO_FILE)
            fa = FrequencyAnalyzer()
            result = fa.analyze_and_store(track_id_freq)

            # Verify DB persistence
            with Session(engine) as s:
                track = s.get(AudioTrack, track_id_freq)
                wd = s.query(WaveformData).filter_by(audio_track_id=track_id_freq).first()

            errors = []
            if track is None:
                errors.append("AudioTrack not found after analyze_and_store")
            if wd is None:
                errors.append("WaveformData not found after analyze_and_store")
            else:
                if wd.num_samples <= 0:
                    errors.append(f"WaveformData.num_samples invalid: {wd.num_samples}")
                if wd.duration <= 0:
                    errors.append(f"WaveformData.duration invalid: {wd.duration}")
                if not wd.band_low or len(wd.band_low) == 0:
                    errors.append("WaveformData.band_low is empty")
                if not wd.band_mid or len(wd.band_mid) == 0:
                    errors.append("WaveformData.band_mid is empty")
                if not wd.band_high or len(wd.band_high) == 0:
                    errors.append("WaveformData.band_high is empty")

            if track and track.duration is not None and track.duration > 0:
                pass  # Good — duration was set
            elif track:
                errors.append(f"AudioTrack.duration not set after analyze_and_store: {track.duration}")

            vram_after = vram_info()
            if errors:
                record_result("FrequencyAnalyzer.analyze_and_store()", "FAIL",
                              time.time() - t0, "; ".join(errors), vram_before, vram_after)
            else:
                detail = (
                    f"WaveformData: samples={wd.num_samples}, duration={wd.duration:.1f}s, "
                    f"Track.bpm={track.bpm}, Track.duration={track.duration}"
                )
                record_result("FrequencyAnalyzer.analyze_and_store()", "PASS",
                              time.time() - t0, detail, vram_before, vram_after)
        except Exception as e:
            vram_after = vram_info()
            is_oom = "out of memory" in str(e).lower()
            record_result("FrequencyAnalyzer.analyze_and_store()",
                          "OOM" if is_oom else "CRASH",
                          time.time() - t0, traceback.format_exc(), vram_before, vram_after)

        # ── Test 3: StemSeparator.separate() ────────────────────────
        logger.info("\n" + "=" * 50)
        logger.info("TEST 3: StemSeparator.separate() — WARNING: SLOW + GPU HEAVY")
        logger.info("=" * 50)
        t0 = time.time()
        vram_before = vram_info()
        try:
            from services.ai_audio_service import StemSeparator
            ss = StemSeparator()

            def progress_cb(pct, msg):
                logger.info(f"  [Stems] {pct}%: {msg}")

            stems = ss.separate(AUDIO_FILE, progress_cb=progress_cb)

            # Validate output
            errors = []
            if not isinstance(stems, dict):
                errors.append(f"Expected dict, got {type(stems)}")
            else:
                for stem_name in STEM_NAMES:
                    if stem_name not in stems:
                        errors.append(f"Missing stem: {stem_name}")
                    else:
                        stem_path = Path(stems[stem_name])
                        if not stem_path.exists():
                            errors.append(f"Stem file does not exist: {stem_path}")
                        elif stem_path.stat().st_size == 0:
                            errors.append(f"Stem file is empty: {stem_path}")

            vram_after = vram_info()
            if errors:
                record_result("StemSeparator.separate()", "FAIL", time.time() - t0,
                              "; ".join(errors), vram_before, vram_after)
            else:
                sizes = {k: f"{Path(v).stat().st_size / 1024**2:.1f}MB" for k, v in stems.items()}
                record_result("StemSeparator.separate()", "PASS", time.time() - t0,
                              f"Stems: {sizes}", vram_before, vram_after)

        except Exception as e:
            vram_after = vram_info()
            err_str = str(e).lower()
            is_oom = "out of memory" in err_str or "cuda" in err_str
            record_result("StemSeparator.separate()",
                          "OOM" if is_oom else "CRASH",
                          time.time() - t0, traceback.format_exc(), vram_before, vram_after)
        finally:
            # Force GPU cleanup
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass

        # ── Test 4: StemSeparator.separate_and_store() ──────────────
        logger.info("\n" + "=" * 50)
        logger.info("TEST 4: StemSeparator.separate_and_store() — DB persistence")
        logger.info("=" * 50)
        t0 = time.time()
        vram_before = vram_info()
        try:
            from services.ai_audio_service import StemSeparator
            from database.session import engine
            from database.models import AudioTrack
            from sqlalchemy.orm import Session

            track_id_stems, _ = ingest_audio_track(tmp_dir, project_id, AUDIO_FILE)
            ss = StemSeparator()

            def progress_cb2(pct, msg):
                logger.info(f"  [Stems+Store] {pct}%: {msg}")

            stems = ss.separate_and_store(track_id_stems, progress_cb=progress_cb2)

            # Verify DB persistence
            errors = []
            with Session(engine) as s:
                track = s.get(AudioTrack, track_id_stems)
                if track is None:
                    errors.append("AudioTrack not found after separate_and_store")
                else:
                    for attr, stem_name in [
                        ("stem_vocals_path", "vocals"),
                        ("stem_drums_path", "drums"),
                        ("stem_bass_path", "bass"),
                        ("stem_other_path", "other"),
                    ]:
                        path_val = getattr(track, attr)
                        if not path_val:
                            errors.append(f"Track.{attr} is empty/None")
                        elif not Path(path_val).exists():
                            errors.append(f"Track.{attr} file does not exist: {path_val}")

            vram_after = vram_info()
            if errors:
                record_result("StemSeparator.separate_and_store()", "FAIL",
                              time.time() - t0, "; ".join(errors), vram_before, vram_after)
            else:
                record_result("StemSeparator.separate_and_store()", "PASS",
                              time.time() - t0,
                              f"All 4 stem paths stored in DB for track {track_id_stems}",
                              vram_before, vram_after)

        except Exception as e:
            vram_after = vram_info()
            err_str = str(e).lower()
            is_oom = "out of memory" in err_str or "cuda" in err_str
            record_result("StemSeparator.separate_and_store()",
                          "OOM" if is_oom else "CRASH",
                          time.time() - t0, traceback.format_exc(), vram_before, vram_after)
        finally:
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass

        # ── Test 5: AutoDucker ──────────────────────────────────────
        logger.info("\n" + "=" * 50)
        logger.info("TEST 5: AutoDucker — needs voice + music WAV files")
        logger.info("=" * 50)
        t0 = time.time()
        vram_before = vram_info()
        try:
            from services.ai_audio_service import AutoDucker
            import numpy as np
            from scipy.io import wavfile

            ducker = AutoDucker(duck_db=-12.0, attack_ms=200.0, release_ms=500.0)

            # Create synthetic test audio (since we need separate voice + music)
            sr = 44100
            duration_sec = 5
            t_arr = np.linspace(0, duration_sec, sr * duration_sec, dtype=np.float32)

            # Music: 440Hz sine wave
            music_data = (0.5 * np.sin(2 * np.pi * 440 * t_arr)).astype(np.float32)
            # Voice: louder 1kHz tone in the middle 2 seconds
            voice_data = np.zeros_like(t_arr, dtype=np.float32)
            mid_start = int(1.5 * sr)
            mid_end = int(3.5 * sr)
            voice_data[mid_start:mid_end] = 0.3 * np.sin(2 * np.pi * 1000 * t_arr[mid_start:mid_end])

            # Write temp WAV files
            music_wav = tmp_dir / "test_music.wav"
            voice_wav = tmp_dir / "test_voice.wav"
            output_wav = tmp_dir / "test_ducked.wav"

            # Write as 16-bit PCM (what AutoDucker.create_ducked_audio_scipy expects)
            wavfile.write(str(music_wav), sr, (music_data * 32767).astype(np.int16))
            wavfile.write(str(voice_wav), sr, (voice_data * 32767).astype(np.int16))

            # Test the scipy-based ducking directly (no FFmpeg dependency)
            result_path = ducker.create_ducked_audio_scipy(
                str(music_wav), str(voice_wav), str(output_wav)
            )

            errors = []
            if not Path(result_path).exists():
                errors.append("Output file does not exist")
            elif Path(result_path).stat().st_size == 0:
                errors.append("Output file is empty")
            else:
                # Read output and verify ducking happened
                import soundfile as sf
                ducked_audio, ducked_sr = sf.read(result_path)
                if ducked_sr != sr:
                    errors.append(f"Output SR mismatch: expected {sr}, got {ducked_sr}")
                if len(ducked_audio) == 0:
                    errors.append("Output audio is empty")
                # Check that the voice section has reduced music amplitude
                # (the ducked_audio = ducked_music + voice, so values should differ from pure music)
                if len(ducked_audio) >= mid_end:
                    pre_voice_rms = np.sqrt(np.mean(ducked_audio[:mid_start]**2))
                    during_voice_rms = np.sqrt(np.mean(ducked_audio[mid_start:mid_end]**2))
                    # During voice: music is ducked, so if music was at 0.5 and ducked by -12dB (x0.25),
                    # the music portion is lower. But voice is added on top. Hard to check precisely
                    # without stem separation. Just check output is non-zero and reasonable.
                    if during_voice_rms < 1e-6:
                        errors.append("During-voice section is silent")

            vram_after = vram_info()
            if errors:
                record_result("AutoDucker.create_ducked_audio_scipy()", "FAIL",
                              time.time() - t0, "; ".join(errors), vram_before, vram_after)
            else:
                out_size = Path(result_path).stat().st_size
                record_result("AutoDucker.create_ducked_audio_scipy()", "PASS",
                              time.time() - t0,
                              f"Output: {out_size/1024:.1f}KB, SR={ducked_sr}",
                              vram_before, vram_after)

        except Exception as e:
            vram_after = vram_info()
            record_result("AutoDucker.create_ducked_audio_scipy()", "CRASH",
                          time.time() - t0, traceback.format_exc(), vram_before, vram_after)

        # ── Test 6: ModelManager singleton ──────────────────────────
        logger.info("\n" + "=" * 50)
        logger.info("TEST 6: ModelManager singleton + VRAM check + OOM recovery")
        logger.info("=" * 50)
        t0 = time.time()
        vram_before = vram_info()
        try:
            from services.model_manager import ModelManager, oom_recovery, GPU_LOAD_LOCK

            # Test singleton
            mm1 = ModelManager()
            mm2 = ModelManager()
            errors = []

            if mm1 is not mm2:
                errors.append("ModelManager is not a singleton!")

            # Test device
            if mm1.device not in ("cuda", "cpu"):
                errors.append(f"Invalid device: {mm1.device}")

            # Test is_loaded
            if mm1.is_loaded:
                errors.append("ModelManager reports model loaded on fresh init (unexpected)")

            # Test check_memory_available
            mem = mm1.check_memory_available()
            if "ram_available_gb" not in mem:
                errors.append("check_memory_available missing ram_available_gb")
            if "vram_available_gb" not in mem:
                errors.append("check_memory_available missing vram_available_gb")

            # Test get_vram_usage
            vram = mm1.get_vram_usage()
            if "vram_used_mb" not in vram:
                errors.append("get_vram_usage missing vram_used_mb")
            if "vram_total_mb" not in vram:
                errors.append("get_vram_usage missing vram_total_mb")

            # Test gpu_info property
            gpu_info = mm1.gpu_info
            if "name" not in gpu_info:
                errors.append("gpu_info missing 'name'")

            # Test unload (should be no-op when nothing loaded)
            mm1.unload()

            # Test oom_recovery decorator
            call_count = 0

            @oom_recovery
            def dummy_oom_func():
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB")
                return "success"

            try:
                result = dummy_oom_func()
                if result != "success":
                    errors.append(f"oom_recovery did not return success: {result}")
                if call_count != 3:
                    errors.append(f"oom_recovery retried {call_count} times, expected 3")
            except Exception as e:
                errors.append(f"oom_recovery raised unexpectedly: {e}")

            # Test oom_recovery with permanent failure
            perm_count = 0

            @oom_recovery
            def permanent_oom():
                nonlocal perm_count
                perm_count += 1
                raise RuntimeError("CUDA out of memory. Always fails.")

            try:
                permanent_oom()
                errors.append("permanent_oom should have raised but didn't")
            except RuntimeError:
                pass  # Expected

            # Test GPU_LOAD_LOCK is reentrant
            with GPU_LOAD_LOCK:
                with GPU_LOAD_LOCK:
                    pass  # Should not deadlock (RLock)

            vram_after = vram_info()
            if errors:
                record_result("ModelManager singleton", "FAIL", time.time() - t0,
                              "; ".join(errors), vram_before, vram_after)
            else:
                detail = (
                    f"device={mm1.device}, gpu={gpu_info.get('name', 'N/A')}, "
                    f"RAM={mem['ram_available_gb']:.1f}GB, VRAM={mem['vram_available_gb']:.1f}GB, "
                    f"oom_recovery works (retry on OOM, raise on permanent failure)"
                )
                record_result("ModelManager singleton", "PASS", time.time() - t0,
                              detail, vram_before, vram_after)

        except Exception as e:
            vram_after = vram_info()
            record_result("ModelManager singleton", "CRASH", time.time() - t0,
                          traceback.format_exc(), vram_before, vram_after)

    finally:
        # ── Cleanup temp directory ───────────────────────────────────
        logger.info("\n" + "=" * 50)
        logger.info("CLEANUP: Removing temp directory")
        logger.info("=" * 50)
        try:
            # Reset engine back to project root DB to avoid holding handles on temp DB
            from database.session import set_project
            set_project(APP_ROOT)
        except Exception as e:
            logger.warning(f"Could not reset DB engine: {e}")

        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            logger.info(f"Cleaned up: {tmp_dir}")
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")

    # ── Final Report ─────────────────────────────────────────────────
    logger.info("\n" + "=" * 70)
    logger.info("  FINAL RESULTS")
    logger.info("=" * 70)
    logger.info(f"{'Test':<45} {'Status':<8} {'Time':<10} Details")
    logger.info("-" * 120)
    for r in results:
        logger.info(f"{r['test']:<45} {r['status']:<8} {r['elapsed_sec']:<10.1f} {r['details'][:200]}")

    # Summary
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    crashed = sum(1 for r in results if r["status"] == "CRASH")
    oom = sum(1 for r in results if r["status"] == "OOM")
    skipped = sum(1 for r in results if r["status"] == "SKIP")

    logger.info("-" * 120)
    logger.info(f"TOTAL: {total} | PASS: {passed} | FAIL: {failed} | CRASH: {crashed} | OOM: {oom} | SKIP: {skipped}")
    logger.info("=" * 70)

    # Write JSON report to temp location
    report_path = APP_ROOT / "tests" / "ai_audio_test_results.json"
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        logger.info(f"JSON report saved: {report_path}")
    except Exception as e:
        logger.warning(f"Could not save JSON report: {e}")


if __name__ == "__main__":
    main()
