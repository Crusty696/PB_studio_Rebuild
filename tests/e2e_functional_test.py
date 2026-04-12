"""PB Studio Rebuild — Vollstaendiger Funktionstest mit echten Daten.

Simuliert den kompletten User-Workflow:
1. Audio importieren → BPM/Beats → Waveform → Key → LUFS → Struktur → Stems
2. Video importieren → SceneDetect → RAFT → SigLIP Embeddings
3. Auto-Edit → Timeline generieren
4. Semantische Video-Suche
5. Export

Nutzt die Service-Schicht direkt (gleiche Logik wie GUI).
Dokumentiert jedes Ergebnis in einem Markdown-Report.

Ausfuehrung:
    .venv310\Scripts\python.exe tests/e2e_functional_test.py [--audio PATH] [--video PATH]
"""

import argparse
import gc
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

# Projekt-Root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
)
logger = logging.getLogger("e2e_test")


# ── Ergebnis-Tracking ──────────────────────────────────────────────────

class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.status = "PENDING"
        self.duration = 0.0
        self.details = {}
        self.error = None

    def ok(self, duration: float, **details):
        self.status = "OK"
        self.duration = duration
        self.details = details

    def fail(self, duration: float, error: str):
        self.status = "FAIL"
        self.duration = duration
        self.error = error

    def skip(self, reason: str):
        self.status = "SKIP"
        self.error = reason


class TestRunner:
    def __init__(self):
        self.results: list[TestResult] = []
        self.audio_id: int | None = None
        self.video_ids: list[int] = []
        self.start_time = time.monotonic()

    def run_test(self, name: str, func, *args, **kwargs):
        """Fuehrt einen Test aus und trackt das Ergebnis."""
        result = TestResult(name)
        logger.info("=" * 60)
        logger.info("TEST: %s", name)
        logger.info("=" * 60)
        t0 = time.monotonic()
        try:
            details = func(*args, **kwargs)
            dur = time.monotonic() - t0
            result.ok(dur, **(details or {}))
            logger.info("  OK (%.1fs) %s", dur, details or "")
        except Exception as e:
            dur = time.monotonic() - t0
            result.fail(dur, f"{type(e).__name__}: {e}")
            logger.error("  FAIL (%.1fs): %s", dur, e)
            logger.debug(traceback.format_exc())
        self.results.append(result)
        return result

    def generate_report(self, output_path: Path) -> str:
        """Generiert einen Markdown Test-Report."""
        total = len(self.results)
        ok = sum(1 for r in self.results if r.status == "OK")
        fail = sum(1 for r in self.results if r.status == "FAIL")
        skip = sum(1 for r in self.results if r.status == "SKIP")
        total_dur = time.monotonic() - self.start_time

        lines = [
            f"# PB Studio — Funktionstest Report",
            f"",
            f"**Datum:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"**Dauer:** {total_dur:.0f}s",
            f"**Ergebnis:** {ok}/{total} OK, {fail} FAIL, {skip} SKIP",
            f"",
            f"## GPU Status",
            f"",
        ]

        try:
            import torch
            lines.append(f"- PyTorch: {torch.__version__}")
            lines.append(f"- CUDA: {torch.cuda.is_available()}")
            if torch.cuda.is_available():
                lines.append(f"- GPU: {torch.cuda.get_device_name(0)}")
                lines.append(f"- VRAM: {torch.cuda.get_device_properties(0).total_memory // (1024**2)} MB")
            else:
                lines.append(f"- GPU: CPU-Modus (kein CUDA)")
        except ImportError:
            lines.append("- PyTorch nicht verfuegbar")

        lines += ["", "## Ergebnisse", "", "| # | Test | Status | Dauer | Details |",
                   "|---|------|--------|-------|---------|"]

        for i, r in enumerate(self.results, 1):
            status_icon = {"OK": "PASS", "FAIL": "FAIL", "SKIP": "SKIP"}.get(r.status, "?")
            detail_str = ""
            if r.error:
                detail_str = r.error[:80]
            elif r.details:
                detail_str = ", ".join(f"{k}={v}" for k, v in list(r.details.items())[:4])
            lines.append(f"| {i} | {r.name} | {status_icon} | {r.duration:.1f}s | {detail_str} |")

        # Detail-Sektionen fuer Failures
        failures = [r for r in self.results if r.status == "FAIL"]
        if failures:
            lines += ["", "## Fehler-Details", ""]
            for r in failures:
                lines += [f"### {r.name}", f"```", f"{r.error}", f"```", ""]

        report = "\n".join(lines)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        logger.info("Report geschrieben: %s", output_path)
        return report


# ── Test-Funktionen ────────────────────────────────────────────────────

def test_database_init():
    """Testet DB-Initialisierung und Schema."""
    from database import init_db, engine, Base
    init_db()
    tables = list(Base.metadata.tables.keys())
    assert len(tables) >= 15, f"Nur {len(tables)} Tabellen (min 15 erwartet)"
    return {"tables": len(tables)}


def test_ollama_connection():
    """Testet Ollama-Verbindung und Modell-Verfuegbarkeit."""
    from services.ollama_client import get_ollama_client
    client = get_ollama_client("http://localhost:11434")
    if not client.is_available():
        raise ConnectionError("Ollama nicht erreichbar auf localhost:11434")
    models = client.list_models()
    best = client.get_best_available_model()
    return {"models": len(models), "best": best}


def test_cuda_status():
    """Testet CUDA/GPU Verfuegbarkeit."""
    import torch
    available = torch.cuda.is_available()
    if available:
        name = torch.cuda.get_device_name(0)
        vram = torch.cuda.get_device_properties(0).total_memory // (1024**2)
        return {"cuda": True, "gpu": name, "vram_mb": vram}
    return {"cuda": False, "device": "cpu"}


def test_audio_import(audio_path: str, runner: TestRunner):
    """Importiert eine Audio-Datei in die DB."""
    from services.ingest_service import ingest_audio
    result = ingest_audio(audio_path)
    assert result and "id" in result, f"Import fehlgeschlagen: {result}"
    runner.audio_id = result["id"]
    return {"audio_id": result["id"], "title": result.get("title", "?"),
            "duration": result.get("duration", 0)}


def test_beat_analysis(audio_id: int):
    """BPM und Beat-Erkennung via beat_this (GPU)."""
    from services.beat_analysis_service import BeatAnalysisService
    svc = BeatAnalysisService()
    result = svc.analyze_and_store(audio_id)
    assert result, "Beat-Analyse gab leeres Ergebnis"
    return {"bpm": result.get("bpm"), "beats": len(result.get("beat_positions", []))}


def test_waveform_analysis(audio_id: int):
    """Rekordbox-Style 3-Band Waveform."""
    from services.audio_service import analyze_waveform_and_store
    result = analyze_waveform_and_store(audio_id)
    assert result, "Waveform-Analyse gab leeres Ergebnis"
    return {"bpm": result.get("bpm"), "samples": result.get("num_samples", 0)}


def test_key_detection(audio_id: int):
    """Musikalische Tonart-Erkennung."""
    from database import engine, AudioTrack
    from sqlalchemy.orm import Session
    with Session(engine) as s:
        track = s.get(AudioTrack, audio_id)
        file_path = track.file_path

    from services.key_detection_service import KeyDetectionService
    svc = KeyDetectionService()
    result = svc.detect_and_store(audio_id, file_path)
    return {"key": result.get("key", "?"), "camelot": result.get("camelot", "?"),
            "confidence": result.get("confidence", 0)}


def test_lufs_analysis(audio_id: int):
    """LUFS Lautstaerke-Analyse (EBU R128)."""
    from database import engine, AudioTrack
    from sqlalchemy.orm import Session
    with Session(engine) as s:
        track = s.get(AudioTrack, audio_id)
        file_path = track.file_path

    from services.lufs_service import LUFSService
    svc = LUFSService()
    result = svc.analyze_and_store(audio_id, file_path)
    return {"integrated": result.get("integrated", 0),
            "loudness_range": result.get("loudness_range", 0)}


def test_structure_detection(audio_id: int):
    """Song-Struktur-Erkennung (INTRO/BUILDUP/DROP/BREAKDOWN/OUTRO)."""
    from database import engine, AudioTrack
    from sqlalchemy.orm import Session
    with Session(engine) as s:
        track = s.get(AudioTrack, audio_id)
        file_path = track.file_path
        bpm = track.bpm

    from services.structure_detection_service import StructureDetectionService
    svc = StructureDetectionService()
    result = svc.detect_and_store(audio_id, file_path, bpm=bpm)
    segments = result.get("segments", [])
    types = [s.get("type", "?") for s in segments]
    return {"segments": len(segments), "types": types[:10]}


def test_stem_separation(audio_id: int):
    """Demucs Stem-Separation (Vocals/Drums/Bass/Other)."""
    from services.ai_audio_service import StemSeparator
    svc = StemSeparator()
    result = svc.separate_and_store(audio_id)
    stems = list(result.keys()) if result else []
    return {"stems": stems}


def test_video_import(video_path: str, runner: TestRunner):
    """Importiert eine Video-Datei in die DB."""
    from services.ingest_service import ingest_video
    result = ingest_video(video_path)
    assert result and "id" in result, f"Import fehlgeschlagen: {result}"
    runner.video_ids.append(result["id"])
    return {"video_id": result["id"], "duration": result.get("duration", 0)}


def test_video_pipeline(video_id: int):
    """Komplette Video-Analyse-Pipeline (SceneDetect → Keyframes → SigLIP)."""
    from database import engine, VideoClip
    from sqlalchemy.orm import Session
    with Session(engine) as s:
        clip = s.get(VideoClip, video_id)
        video_path = clip.file_path

    from services.video_analysis_service import run_full_pipeline
    result = run_full_pipeline(video_path=video_path, video_clip_id=video_id)
    return {"scenes": len(result.scenes), "embeddings": result.embeddings_stored}


def test_semantic_search(query: str = "person dancing"):
    """SigLIP semantische Video-Suche."""
    from services.vector_db_service import VectorDBService
    vdb = VectorDBService()
    results = vdb.search_by_text(query, limit=5)
    return {"query": query, "results": len(results)}


def test_pacing_strategist():
    """Gemma 4 Pacing-Plan-Generierung via Ollama."""
    from services.pacing_strategist import PacingStrategist
    ps = PacingStrategist()
    plan = ps.generate_pacing_plan(
        sections=[
            {"type": "WARMUP", "start": 0, "end": 60, "avg_energy": 0.3},
            {"type": "DROP", "start": 60, "end": 120, "avg_energy": 0.9},
            {"type": "BREAKDOWN", "start": 120, "end": 180, "avg_energy": 0.2},
        ],
        bpm=140,
        total_duration=180,
        clip_count=10,
    )
    return {"sections": len(plan.section_overrides),
            "min_duration": plan.global_min_duration,
            "variety": plan.variety_priority}


def test_action_registry():
    """Prueft ob alle erwarteten Aktionen registriert sind."""
    from services.actions import audio_actions, video_actions, edit_actions, ai_actions
    from services.action_registry import action_registry
    actions = action_registry.list_actions()
    expected = [
        "analyze_audio", "separate_stems", "analyze_video",
        "auto_edit", "export_timeline", "search_video",
        "detect_key", "analyze_lufs", "detect_structure",
    ]
    missing = [a for a in expected if a not in actions]
    assert not missing, f"Fehlende Aktionen: {missing}"
    return {"total": len(actions), "missing": 0}


def test_auto_edit(audio_id: int, video_ids: list[int]):
    """Auto-Edit: Generiert Timeline basierend auf Beats und Videos."""
    if not video_ids:
        raise ValueError("Keine Videos importiert — Auto-Edit nicht moeglich")
    from services.pacing_service import calculate_cut_points
    from database import engine, Beatgrid
    from sqlalchemy.orm import Session

    with Session(engine) as s:
        bg = s.query(Beatgrid).filter_by(audio_track_id=audio_id).first()
        if not bg or not bg.beat_positions:
            raise ValueError("Kein Beatgrid fuer Audio — erst Beat-Analyse ausfuehren")
        beats = json.loads(bg.beat_positions) if isinstance(bg.beat_positions, str) else bg.beat_positions
        bpm = bg.bpm

    cut_points = calculate_cut_points(beats, total_duration=len(beats) / (bpm / 60), bpm=bpm)
    return {"bpm": bpm, "beats": len(beats), "cut_points": len(cut_points)}


# ── Main ───────────────────────────────────────────────────────────────

def find_test_files():
    """Sucht nach Test-Audio/Video-Dateien im Projekt."""
    storage = PROJECT_ROOT / "storage"
    audio_exts = {".mp3", ".wav", ".flac", ".ogg", ".m4a"}
    video_exts = {".mp4", ".mov", ".avi", ".mkv"}

    audio_files = []
    video_files = []

    for search_dir in [PROJECT_ROOT, storage, Path.home() / "Music", Path.home() / "Videos"]:
        if not search_dir.exists():
            continue
        for f in search_dir.rglob("*"):
            if f.suffix.lower() in audio_exts and f.stat().st_size > 100_000:
                audio_files.append(str(f))
            elif f.suffix.lower() in video_exts and f.stat().st_size > 100_000:
                video_files.append(str(f))
            if len(audio_files) >= 3 and len(video_files) >= 3:
                break

    return audio_files[:1], video_files[:3]


def main():
    parser = argparse.ArgumentParser(description="PB Studio E2E Funktionstest")
    parser.add_argument("--audio", help="Pfad zur Test-Audio-Datei")
    parser.add_argument("--video", action="append", help="Pfad zu Test-Video-Datei(en)")
    parser.add_argument("--skip-gpu", action="store_true", help="GPU-Tests ueberspringen")
    parser.add_argument("--skip-stems", action="store_true", help="Stem-Separation ueberspringen (langsam)")
    parser.add_argument("--report", default="test-report/e2e-functional-report.md",
                       help="Pfad fuer den Report")
    args = parser.parse_args()

    runner = TestRunner()

    print("=" * 60)
    print("  PB STUDIO — VOLLSTAENDIGER FUNKTIONSTEST")
    print("=" * 60)

    # ── Phase 0: System-Checks ──
    runner.run_test("Database Init", test_database_init)
    runner.run_test("Ollama Verbindung", test_ollama_connection)
    runner.run_test("CUDA/GPU Status", test_cuda_status)
    runner.run_test("Action Registry", test_action_registry)

    # ── Phase 1: Audio-Workflow ──
    audio_path = args.audio
    if not audio_path:
        auto_audio, auto_video = find_test_files()
        audio_path = auto_audio[0] if auto_audio else None

    if audio_path and Path(audio_path).exists():
        runner.run_test("Audio Import", test_audio_import, audio_path, runner)

        if runner.audio_id:
            runner.run_test("Beat-Analyse (beat_this)", test_beat_analysis, runner.audio_id)
            runner.run_test("Waveform-Analyse", test_waveform_analysis, runner.audio_id)
            runner.run_test("Key-Erkennung", test_key_detection, runner.audio_id)
            runner.run_test("LUFS-Analyse", test_lufs_analysis, runner.audio_id)
            runner.run_test("Struktur-Erkennung", test_structure_detection, runner.audio_id)

            if not args.skip_stems:
                runner.run_test("Stem-Separation (Demucs)", test_stem_separation, runner.audio_id)
            else:
                r = TestResult("Stem-Separation (Demucs)")
                r.skip("--skip-stems")
                runner.results.append(r)
    else:
        logger.warning("Keine Audio-Datei angegeben oder gefunden. Audio-Tests uebersprungen.")

    # ── Phase 2: Video-Workflow ──
    video_paths = args.video or []
    if not video_paths:
        _, auto_video = find_test_files()
        video_paths = auto_video

    for vp in video_paths[:3]:
        if Path(vp).exists():
            runner.run_test(f"Video Import: {Path(vp).name}", test_video_import, vp, runner)

    if runner.video_ids:
        runner.run_test("Video-Pipeline (Scene+RAFT+SigLIP)",
                       test_video_pipeline, runner.video_ids[0])
        runner.run_test("Semantische Video-Suche", test_semantic_search)

    # ── Phase 3: KI / Pacing ──
    runner.run_test("Pacing-Strategist (Gemma 4)", test_pacing_strategist)

    if runner.audio_id and runner.video_ids:
        runner.run_test("Auto-Edit (Cut-Points)", test_auto_edit,
                       runner.audio_id, runner.video_ids)

    # ── Report ──
    report_path = PROJECT_ROOT / args.report
    report = runner.generate_report(report_path)
    print()
    print(report)


if __name__ == "__main__":
    main()
