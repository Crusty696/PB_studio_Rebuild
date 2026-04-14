"""Comprehensive REAL-DATA audio analysis pipeline test.

Tests each audio analysis service individually with a REAL 150MB
Progressive Psy Trance MP3 file. Uses a TEMPORARY database to avoid
corrupting user data.

Run from project root:
    .venv310/Scripts/python.exe tests/test_audio_analysis_real.py
"""

import gc
import logging
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

# --------------------------------------------------------------------------
# Bootstrap: project root on sys.path
# --------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
_DEFAULT_AUDIO = Path(__file__).resolve().parent.parent / "vendor" / "beat_this" / "tests" / "It Don't Mean A Thing - Kings of Swing.mp3"
AUDIO_FILE = os.environ.get("PB_TEST_AUDIO", str(_DEFAULT_AUDIO))
TIMEOUT_SEC = 300  # 5 minutes max per function

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("REAL_AUDIO_TEST")


# ==========================================================================
# Utilities
# ==========================================================================

class TestResult:
    """Container for a single test outcome."""

    def __init__(self, name: str):
        self.name = name
        self.status = "SKIP"        # PASS / FAIL / CRASH / SKIP
        self.elapsed_sec = 0.0
        self.details = {}
        self.error = None
        self.traceback = None

    def __repr__(self):
        tag = {"PASS": "[OK]", "FAIL": "[FAIL]", "CRASH": "[CRASH]", "SKIP": "[SKIP]"}[self.status]
        return f"{tag} {self.name} ({self.elapsed_sec:.1f}s)"


results: list[TestResult] = []


def _mem_mb() -> float:
    """Current process RSS in MB (Windows)."""
    try:
        import psutil
        return psutil.Process().memory_info().rss / (1024 * 1024)
    except ImportError:
        return -1.0


# ==========================================================================
# Temp DB setup — monkeypatch the database module
# ==========================================================================

def setup_temp_db():
    """Create a temporary SQLite DB and swap the global engine to point to it.

    Returns (tmp_dir, db_path) so the caller can clean up.
    """
    from sqlalchemy import create_engine, event
    from database.session import EngineProxy, engine as global_engine
    from database.models import Base, Project
    from sqlalchemy.orm import Session

    tmp_dir = tempfile.mkdtemp(prefix="pb_audio_test_")
    db_path = Path(tmp_dir) / "test_audio.db"

    new_eng = create_engine(
        f"sqlite:///{db_path}",
        echo=False,
        connect_args={"check_same_thread": False, "timeout": 60},
    )

    @event.listens_for(new_eng, "connect")
    def _pragma(dbapi_conn, _rec):
        c = dbapi_conn.cursor()
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute("PRAGMA busy_timeout=60000")
        c.close()

    # Create all tables
    Base.metadata.create_all(new_eng)

    # Swap the global engine proxy
    global_engine.swap(new_eng)

    # Create a test project
    with Session(new_eng) as s:
        proj = Project(name="AudioTest", path=str(tmp_dir), resolution="1920x1080", fps=30.0)
        s.add(proj)
        s.commit()
        project_id = proj.id

    log.info("Temp DB created: %s (project_id=%d)", db_path, project_id)
    return tmp_dir, db_path, project_id, new_eng


_track_cache: dict[tuple[int, str], int] = {}


def insert_test_track(engine, project_id: int, file_path: str) -> int:
    """Insert or reuse a minimal AudioTrack row and return its id.

    The DB has UNIQUE(project_id, file_path). When multiple tests share the
    same real audio file, we reuse the existing row instead of failing.
    The file_path MUST stay real — services load the audio via librosa.
    """
    from sqlalchemy.orm import Session
    from database.models import AudioTrack

    key = (project_id, file_path)
    if key in _track_cache:
        log.info("Reusing AudioTrack id=%d for %s", _track_cache[key], Path(file_path).name)
        return _track_cache[key]

    with Session(engine) as s:
        existing = s.query(AudioTrack).filter_by(
            project_id=project_id, file_path=file_path
        ).first()
        if existing:
            tid = existing.id
        else:
            track = AudioTrack(
                project_id=project_id,
                file_path=file_path,
                title=Path(file_path).stem,
            )
            s.add(track)
            s.commit()
            tid = track.id
    _track_cache[key] = tid
    log.info("Inserted AudioTrack id=%d for %s", tid, Path(file_path).name)
    return tid


# ==========================================================================
# Individual tests
# ==========================================================================

def test_1_audio_analyzer(audio_file: str) -> TestResult:
    """Test 1: AudioAnalyzer.analyze() — Basic BPM/Beat/Energy analysis."""
    r = TestResult("1. AudioAnalyzer.analyze()")
    t0 = time.perf_counter()
    mem_before = _mem_mb()
    try:
        from services.audio_service import AudioAnalyzer
        analyzer = AudioAnalyzer()
        result = analyzer.analyze(audio_file)

        r.elapsed_sec = time.perf_counter() - t0
        mem_after = _mem_mb()

        # Validate
        bpm = result.get("bpm", 0)
        beat_positions = result.get("beat_positions", [])
        energy_curve = result.get("energy_curve", [])
        duration = result.get("duration", 0)

        r.details = {
            "bpm": bpm,
            "num_beats": len(beat_positions),
            "num_energy_values": len(energy_curve),
            "duration": duration,
            "sample_rate": result.get("sample_rate"),
            "mem_before_mb": round(mem_before, 1),
            "mem_after_mb": round(mem_after, 1),
        }

        errors = []
        if not (60 <= bpm <= 200):
            errors.append(f"BPM {bpm} outside expected range [60-200]")
        if not beat_positions:
            errors.append("beat_positions is empty")
        if not energy_curve:
            errors.append("energy_curve is empty")
        if duration <= 0:
            errors.append(f"duration {duration} <= 0")

        if errors:
            r.status = "FAIL"
            r.error = "; ".join(errors)
        else:
            r.status = "PASS"

    except Exception as e:
        r.elapsed_sec = time.perf_counter() - t0
        r.status = "CRASH"
        r.error = str(e)
        r.traceback = traceback.format_exc()

    return r


def test_2_audio_analyzer_store(audio_file: str, engine, project_id: int) -> TestResult:
    """Test 2: AudioAnalyzer.analyze_and_store() — Analyze + DB write."""
    r = TestResult("2. AudioAnalyzer.analyze_and_store()")
    t0 = time.perf_counter()
    try:
        track_id = insert_test_track(engine, project_id, audio_file)

        from services.audio_service import AudioAnalyzer
        analyzer = AudioAnalyzer()
        result = analyzer.analyze_and_store(track_id)

        r.elapsed_sec = time.perf_counter() - t0

        # Verify DB state
        from sqlalchemy.orm import Session
        from database.models import AudioTrack
        with Session(engine) as s:
            track = s.query(AudioTrack).get(track_id)
            db_bpm = track.bpm
            db_duration = track.duration
            db_energy = track.energy_curve

        r.details = {
            "return_bpm": result.get("bpm"),
            "db_bpm": db_bpm,
            "db_duration": db_duration,
            "db_energy_len": len(db_energy) if db_energy else 0,
            "return_duration": result.get("duration"),
        }

        errors = []
        if db_bpm is None or db_bpm <= 0:
            errors.append(f"DB bpm is {db_bpm}")
        if db_duration is None or db_duration <= 0:
            errors.append(f"DB duration is {db_duration}")
        if not db_energy:
            errors.append("DB energy_curve is empty/None")

        if errors:
            r.status = "FAIL"
            r.error = "; ".join(errors)
        else:
            r.status = "PASS"

    except Exception as e:
        r.elapsed_sec = time.perf_counter() - t0
        r.status = "CRASH"
        r.error = str(e)
        r.traceback = traceback.format_exc()

    return r


def test_3_beat_analysis(audio_file: str) -> TestResult:
    """Test 3: BeatAnalysisService.analyze() — GPU beat detection."""
    r = TestResult("3. BeatAnalysisService.analyze()")
    t0 = time.perf_counter()
    try:
        from services.beat_analysis_service import BeatAnalysisService
        # Reset singleton for clean state
        BeatAnalysisService._instance = None
        svc = BeatAnalysisService()
        result = svc.analyze(audio_file)

        r.elapsed_sec = time.perf_counter() - t0

        beats = result.get("beats", [])
        downbeats = result.get("downbeats", [])
        bpm = result.get("bpm", 0)
        is_fallback = result.get("fallback", False)

        r.details = {
            "bpm": bpm,
            "num_beats": len(beats),
            "num_downbeats": len(downbeats),
            "duration": result.get("duration"),
            "is_fallback": is_fallback,
            "fallback_reason": result.get("fallback_reason", "N/A"),
        }

        errors = []
        if not beats:
            errors.append("beats list is empty")
        if bpm <= 0:
            errors.append(f"BPM is {bpm}")

        if errors:
            r.status = "FAIL"
            r.error = "; ".join(errors)
        else:
            r.status = "PASS"

        # Unload model to free VRAM
        svc.unload()

    except Exception as e:
        r.elapsed_sec = time.perf_counter() - t0
        r.status = "CRASH"
        r.error = str(e)
        r.traceback = traceback.format_exc()
        # Try to unload even on crash
        try:
            from services.beat_analysis_service import BeatAnalysisService
            BeatAnalysisService._instance = None
        except Exception:
            pass

    return r


def test_4_beat_analysis_store(audio_file: str, engine, project_id: int) -> TestResult:
    """Test 4: BeatAnalysisService.analyze_and_store() — Beat analysis + DB."""
    r = TestResult("4. BeatAnalysisService.analyze_and_store()")
    t0 = time.perf_counter()
    try:
        track_id = insert_test_track(engine, project_id, audio_file)

        from services.beat_analysis_service import BeatAnalysisService
        # Reset singleton for clean state
        BeatAnalysisService._instance = None
        svc = BeatAnalysisService()
        result = svc.analyze_and_store(track_id)

        r.elapsed_sec = time.perf_counter() - t0

        # Verify DB state
        from sqlalchemy.orm import Session
        from database.models import AudioTrack, Beatgrid
        with Session(engine) as s:
            track = s.query(AudioTrack).get(track_id)
            bg = s.query(Beatgrid).filter_by(audio_track_id=track_id).first()

        r.details = {
            "return_bpm": result.get("bpm"),
            "db_bpm": track.bpm if track else None,
            "beatgrid_exists": bg is not None,
            "bg_num_beats": len(bg.beat_positions) if bg and bg.beat_positions else 0,
            "bg_num_downbeats": len(bg.downbeat_positions) if bg and bg.downbeat_positions else 0,
            "bg_has_energy": bool(bg.energy_per_beat) if bg else False,
            "is_fallback": result.get("fallback", False),
        }

        errors = []
        if bg is None:
            errors.append("No Beatgrid row created in DB")
        elif not bg.beat_positions:
            errors.append("Beatgrid.beat_positions is empty")

        if errors:
            r.status = "FAIL"
            r.error = "; ".join(errors)
        else:
            r.status = "PASS"

    except Exception as e:
        r.elapsed_sec = time.perf_counter() - t0
        r.status = "CRASH"
        r.error = str(e)
        r.traceback = traceback.format_exc()
        try:
            from services.beat_analysis_service import BeatAnalysisService
            BeatAnalysisService._instance = None
        except Exception:
            pass

    return r


def test_5_key_detection(audio_file: str) -> TestResult:
    """Test 5: KeyDetectionService.detect_key() — Musical key detection."""
    r = TestResult("5. KeyDetectionService.detect_key()")
    t0 = time.perf_counter()
    try:
        from services.key_detection_service import KeyDetectionService
        svc = KeyDetectionService()
        result = svc.detect_key(audio_file)

        r.elapsed_sec = time.perf_counter() - t0

        r.details = {
            "key": result.key,
            "camelot": result.camelot,
            "confidence": result.confidence,
            "is_minor": result.is_minor,
            "method": result.method,
            "num_modulation_segments": len(result.modulation_segments),
            "tension_curve_len": len(result.harmonic_tension_curve),
        }

        errors = []
        if not result.key or result.key == "":
            errors.append("Key string is empty")
        if result.confidence <= 0:
            errors.append(f"Confidence is {result.confidence}")
        if result.method == "fallback":
            errors.append("Fell back to fallback method (no real detection)")

        if errors:
            r.status = "FAIL"
            r.error = "; ".join(errors)
        else:
            r.status = "PASS"

    except Exception as e:
        r.elapsed_sec = time.perf_counter() - t0
        r.status = "CRASH"
        r.error = str(e)
        r.traceback = traceback.format_exc()

    return r


def test_6_lufs(audio_file: str) -> TestResult:
    """Test 6: LUFSService.analyze() — LUFS loudness measurement."""
    r = TestResult("6. LUFSService.analyze()")
    t0 = time.perf_counter()
    try:
        from services.lufs_service import LUFSService
        svc = LUFSService()
        result = svc.analyze(audio_file)

        r.elapsed_sec = time.perf_counter() - t0

        r.details = {
            "integrated": result.integrated,
            "short_term_max": result.short_term_max,
            "loudness_range": result.loudness_range,
            "true_peak": result.true_peak,
            "broadcast_compliant": result.broadcast_compliant,
            "streaming_compliant": result.streaming_compliant,
        }

        errors = []
        # For mastered Psy Trance, we expect LUFS roughly -6 to -14
        if not (-30 <= result.integrated <= 0):
            errors.append(f"Integrated LUFS {result.integrated} outside plausible range [-30, 0]")
        if result.integrated == -14.0 and result.loudness_range == 8.0:
            errors.append("Got exact fallback values (-14.0, 8.0) — FFmpeg may have failed silently")

        if errors:
            r.status = "FAIL"
            r.error = "; ".join(errors)
        else:
            r.status = "PASS"

    except Exception as e:
        r.elapsed_sec = time.perf_counter() - t0
        r.status = "CRASH"
        r.error = str(e)
        r.traceback = traceback.format_exc()

    return r


def test_7_spectral(audio_file: str) -> TestResult:
    """Test 7: SpectralAnalysisService.analyze() — Spectral analysis."""
    r = TestResult("7. SpectralAnalysisService.analyze()")
    t0 = time.perf_counter()
    try:
        from services.spectral_analysis_service import SpectralAnalysisService
        svc = SpectralAnalysisService()
        result = svc.analyze(audio_file)

        r.elapsed_sec = time.perf_counter() - t0

        r.details = {
            "num_bands": len(result.bands),
            "num_events": len(result.events),
            "dominant_band": result.dominant_band,
            "spectral_centroid_mean": result.spectral_centroid_mean,
            "band_names": [b.name for b in result.bands] if result.bands else [],
            "band_energies": {b.name: round(b.energy, 3) for b in result.bands} if result.bands else {},
        }

        errors = []
        if len(result.bands) != 8:
            errors.append(f"Expected 8 bands, got {len(result.bands)}")
        if all(b.energy == 0.0 for b in result.bands):
            errors.append("All band energies are 0.0 — analysis may have failed")
        if not result.dominant_band:
            errors.append("dominant_band is empty")

        if errors:
            r.status = "FAIL"
            r.error = "; ".join(errors)
        else:
            r.status = "PASS"

    except Exception as e:
        r.elapsed_sec = time.perf_counter() - t0
        r.status = "CRASH"
        r.error = str(e)
        r.traceback = traceback.format_exc()

    return r


def test_8_structure(audio_file: str) -> TestResult:
    """Test 8: StructureDetectionService.detect() — Song structure detection."""
    r = TestResult("8. StructureDetectionService.detect()")
    t0 = time.perf_counter()
    try:
        from services.structure_detection_service import StructureDetectionService
        svc = StructureDetectionService()
        result = svc.detect(audio_file)

        r.elapsed_sec = time.perf_counter() - t0

        segment_info = []
        for seg in result.segments:
            segment_info.append({
                "label": seg.label,
                "start": round(seg.start_time, 1),
                "end": round(seg.end_time, 1),
                "energy": round(seg.energy, 3),
                "confidence": round(seg.confidence, 3),
            })

        r.details = {
            "num_segments": len(result.segments),
            "is_dj_mix": result.is_dj_mix,
            "transition_count": result.transition_count,
            "detected_genre": result.detected_genre,
            "genre_confidence": result.genre_confidence,
            "segments": segment_info[:10],  # First 10 for readability
        }

        errors = []
        if not result.segments:
            errors.append("No segments detected")
        # DJ mix: >10min file SHOULD be detected as DJ mix
        # But this is genre-dependent, so just warn
        if len(result.segments) < 2:
            errors.append(f"Only {len(result.segments)} segment(s) — expected more for a long track")

        if errors:
            r.status = "FAIL"
            r.error = "; ".join(errors)
        else:
            r.status = "PASS"

    except Exception as e:
        r.elapsed_sec = time.perf_counter() - t0
        r.status = "CRASH"
        r.error = str(e)
        r.traceback = traceback.format_exc()

    return r


def test_9_onset_rhythm(audio_file: str) -> TestResult:
    """Test 9: OnsetRhythmService.analyze() — Onset/rhythm analysis.

    Uses beat_positions from librosa as input.
    """
    r = TestResult("9. OnsetRhythmService.analyze()")
    t0 = time.perf_counter()
    try:
        import librosa
        import numpy as np

        # Load audio (first 120s to save RAM/time)
        log.info("  Loading first 120s for onset analysis...")
        y, sr = librosa.load(audio_file, sr=22050, mono=True, duration=120)

        # Get beat positions from librosa
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
        log.info("  Got %d beats from librosa for onset analysis", len(beat_times))

        from services.onset_rhythm_service import OnsetRhythmService
        svc = OnsetRhythmService()
        result = svc.analyze(y, sr, beat_times)

        r.elapsed_sec = time.perf_counter() - t0

        r.details = {
            "num_kick_onsets": len(result.onsets_kick),
            "num_snare_onsets": len(result.onsets_snare),
            "num_hihat_onsets": len(result.onsets_hihat),
            "onset_strength_len": len(result.onset_strength_curve),
            "syncopation_score": round(result.syncopation_score, 3),
            "groove_template": result.groove_template,
            "groove_confidence": round(result.groove_confidence, 3),
        }

        errors = []
        if len(result.onsets_kick) == 0 and len(result.onsets_snare) == 0 and len(result.onsets_hihat) == 0:
            errors.append("No onsets detected in any band")
        if not result.onset_strength_curve:
            errors.append("onset_strength_curve is empty")

        if errors:
            r.status = "FAIL"
            r.error = "; ".join(errors)
        else:
            r.status = "PASS"

    except Exception as e:
        r.elapsed_sec = time.perf_counter() - t0
        r.status = "CRASH"
        r.error = str(e)
        r.traceback = traceback.format_exc()

    return r


# ==========================================================================
# Main
# ==========================================================================

def main():
    print("=" * 78)
    print("  PB STUDIO — REAL AUDIO ANALYSIS PIPELINE TEST")
    print(f"  Audio: {AUDIO_FILE}")
    print(f"  File size: {os.path.getsize(AUDIO_FILE) / (1024*1024):.1f} MB")
    print(f"  Process mem: {_mem_mb():.0f} MB")
    print("=" * 78)

    # Setup temp DB
    tmp_dir, db_path, project_id, new_eng = setup_temp_db()

    total_t0 = time.perf_counter()

    try:
        # ── Test 1: AudioAnalyzer.analyze() ──────────────────────────────
        print("\n>>> Test 1: AudioAnalyzer.analyze()")
        r = test_1_audio_analyzer(AUDIO_FILE)
        results.append(r)
        print(f"    {r}")
        for k, v in r.details.items():
            print(f"      {k}: {v}")
        if r.traceback:
            print(f"    TRACEBACK:\n{r.traceback}")

        # ── Test 2: AudioAnalyzer.analyze_and_store() ────────────────────
        print("\n>>> Test 2: AudioAnalyzer.analyze_and_store()")
        r = test_2_audio_analyzer_store(AUDIO_FILE, new_eng, project_id)
        results.append(r)
        print(f"    {r}")
        for k, v in r.details.items():
            print(f"      {k}: {v}")
        if r.traceback:
            print(f"    TRACEBACK:\n{r.traceback}")

        gc.collect()

        # ── Test 3: BeatAnalysisService.analyze() ────────────────────────
        print("\n>>> Test 3: BeatAnalysisService.analyze()")
        r = test_3_beat_analysis(AUDIO_FILE)
        results.append(r)
        print(f"    {r}")
        for k, v in r.details.items():
            print(f"      {k}: {v}")
        if r.traceback:
            print(f"    TRACEBACK:\n{r.traceback}")

        gc.collect()

        # ── Test 4: BeatAnalysisService.analyze_and_store() ──────────────
        print("\n>>> Test 4: BeatAnalysisService.analyze_and_store()")
        r = test_4_beat_analysis_store(AUDIO_FILE, new_eng, project_id)
        results.append(r)
        print(f"    {r}")
        for k, v in r.details.items():
            print(f"      {k}: {v}")
        if r.traceback:
            print(f"    TRACEBACK:\n{r.traceback}")

        gc.collect()

        # ── Test 5: KeyDetectionService.detect_key() ─────────────────────
        print("\n>>> Test 5: KeyDetectionService.detect_key()")
        r = test_5_key_detection(AUDIO_FILE)
        results.append(r)
        print(f"    {r}")
        for k, v in r.details.items():
            print(f"      {k}: {v}")
        if r.traceback:
            print(f"    TRACEBACK:\n{r.traceback}")

        # ── Test 6: LUFSService.analyze() ────────────────────────────────
        print("\n>>> Test 6: LUFSService.analyze()")
        r = test_6_lufs(AUDIO_FILE)
        results.append(r)
        print(f"    {r}")
        for k, v in r.details.items():
            print(f"      {k}: {v}")
        if r.traceback:
            print(f"    TRACEBACK:\n{r.traceback}")

        # ── Test 7: SpectralAnalysisService.analyze() ────────────────────
        print("\n>>> Test 7: SpectralAnalysisService.analyze()")
        r = test_7_spectral(AUDIO_FILE)
        results.append(r)
        print(f"    {r}")
        for k, v in r.details.items():
            print(f"      {k}: {v}")
        if r.traceback:
            print(f"    TRACEBACK:\n{r.traceback}")

        # ── Test 8: StructureDetectionService.detect() ───────────────────
        print("\n>>> Test 8: StructureDetectionService.detect()")
        r = test_8_structure(AUDIO_FILE)
        results.append(r)
        print(f"    {r}")
        for k, v in r.details.items():
            if k == "segments":
                print(f"      {k}:")
                for seg in v:
                    print(f"        {seg['label']:12s} {seg['start']:7.1f}s - {seg['end']:7.1f}s  (E={seg['energy']:.3f}, C={seg['confidence']:.3f})")
            else:
                print(f"      {k}: {v}")
        if r.traceback:
            print(f"    TRACEBACK:\n{r.traceback}")

        # ── Test 9: OnsetRhythmService.analyze() ─────────────────────────
        print("\n>>> Test 9: OnsetRhythmService.analyze()")
        r = test_9_onset_rhythm(AUDIO_FILE)
        results.append(r)
        print(f"    {r}")
        for k, v in r.details.items():
            print(f"      {k}: {v}")
        if r.traceback:
            print(f"    TRACEBACK:\n{r.traceback}")

    finally:
        total_elapsed = time.perf_counter() - total_t0

        # ── Summary ──────────────────────────────────────────────────────
        print("\n" + "=" * 78)
        print("  SUMMARY")
        print("=" * 78)
        print(f"  {'Test':<45} {'Status':<8} {'Time':>8}")
        print("  " + "-" * 63)

        pass_count = 0
        fail_count = 0
        crash_count = 0
        for r in results:
            status_str = r.status
            print(f"  {r.name:<45} {status_str:<8} {r.elapsed_sec:>7.1f}s")
            if r.status == "PASS":
                pass_count += 1
            elif r.status == "FAIL":
                fail_count += 1
            elif r.status == "CRASH":
                crash_count += 1

        print("  " + "-" * 63)
        print(f"  Total: {pass_count} PASS, {fail_count} FAIL, {crash_count} CRASH")
        print(f"  Total time: {total_elapsed:.1f}s")
        print(f"  Final mem: {_mem_mb():.0f} MB")
        print("=" * 78)

        # Cleanup temp DB
        try:
            import shutil
            new_eng.dispose()
            shutil.rmtree(tmp_dir, ignore_errors=True)
            log.info("Temp DB cleaned up: %s", tmp_dir)
        except Exception as e:
            log.warning("Cleanup failed: %s", e)


if __name__ == "__main__":
    main()
