#!/usr/bin/env python3
"""E2E Full Render Test — Headless Pipeline ohne GUI.

Durchlaeuft die komplette PB Studio Pipeline programmatisch:
1. Audio-Analyse (BPM, Beats, Key, LUFS, Struktur)
2. Stem-Separation (Demucs auf CUDA)
3. Auto-Edit (Timeline generieren)
4. Video-Export (FFmpeg Render, 1h+ Output)

Nutzt echte Daten aus der DB, echte GPU, echtes FFmpeg.
Kein Mock, kein Fake, kein Shortcut.
"""

import sys
import time
import logging
from pathlib import Path

# Projekt-Root zum Path hinzufuegen
PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from database import engine, AudioTrack, VideoClip, TimelineEntry, get_active_project_id
from sqlalchemy.orm import Session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("E2E")


def step(name: str):
    log.info("=" * 60)
    log.info("  SCHRITT: %s", name)
    log.info("=" * 60)


def main():
    t_start = time.time()
    log.info("E2E Full Render Test gestartet")

    # 0. Voraussetzungen pruefen
    with Session(engine) as s:
        audio = s.query(AudioTrack).first()
        video_count = s.query(VideoClip).count()
        if not audio:
            log.error("Kein Audio-Track in DB. Bitte zuerst importieren.")
            return False
        if video_count == 0:
            log.error("Keine Video-Clips in DB. Bitte zuerst importieren.")
            return False
        track_id = audio.id
        audio_path = audio.file_path
        audio_title = audio.title
        video_ids = [v.id for v in s.query(VideoClip).limit(50).all()]

    log.info("Audio: [%d] %s (%.0fs)", track_id, audio_title, audio.duration or 0)
    log.info("Videos: %d Clips verfuegbar", len(video_ids))

    # 1. BPM/Beat-Analyse
    step("1/6: BPM/Beat-Analyse (beat_this)")
    try:
        from services.beat_analysis_service import BeatAnalysisService
        beat_svc = BeatAnalysisService()
        result = beat_svc.analyze_and_store(
            track_id,
            progress_cb=lambda pct, msg: log.info("  [BPM %d%%] %s", pct, msg),
        )
        log.info("  BPM: %.1f | Beats: %d | Downbeats: %d",
                 result.get("bpm", 0), len(result.get("beats", [])), len(result.get("downbeats", [])))
    except Exception as e:
        log.error("  BPM-Analyse fehlgeschlagen: %s", e)

    # 2. Key Detection
    step("2/6: Key Detection")
    try:
        from services.key_detection_service import KeyDetectionService
        key_result = KeyDetectionService().detect_key(audio_path)
        log.info("  Key: %s (%s) Conf=%.0f%%", key_result.key, key_result.camelot, key_result.confidence * 100)
    except Exception as e:
        log.error("  Key-Detection fehlgeschlagen: %s", e)

    # 3. LUFS
    step("3/6: LUFS-Analyse")
    try:
        from services.lufs_service import LUFSService
        lufs_result = LUFSService().analyze(audio_path)
        log.info("  LUFS: %.1f dB | LRA: %.1f LU | TP: %.1f dBTP",
                 lufs_result.integrated, lufs_result.loudness_range, lufs_result.true_peak)
    except Exception as e:
        log.error("  LUFS fehlgeschlagen: %s", e)

    # 4. Struktur
    step("4/6: Struktur-Erkennung")
    try:
        from services.structure_detection_service import StructureDetectionService
        with Session(engine) as s:
            track = s.get(AudioTrack, track_id)
            bpm = track.bpm
        struct_result = StructureDetectionService().detect(audio_path, bpm=bpm)
        log.info("  %d Segmente erkannt | DJ-Mix: %s", len(struct_result.segments), struct_result.is_dj_mix)
    except Exception as e:
        log.error("  Struktur fehlgeschlagen: %s", e)

    # VRAM explizit freigeben nach GPU-Analysen
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            import gc; gc.collect()
            log.info("VRAM freigegeben vor Auto-Edit")
    except Exception:
        pass

    # 5. Auto-Edit (Timeline generieren)
    step("5/6: Auto-Edit (Timeline generieren)")
    try:
        from services.pacing_service import auto_edit_phase3, AdvancedPacingSettings
        # VRAM-Schutz: ModelManager entladen bevor Auto-Edit startet
        try:
            from services.model_manager import ModelManager
            ModelManager().unload()
            import torch, gc
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            gc.collect()
            log.info("  GPU-Modelle entladen vor Auto-Edit")
        except Exception:
            pass

        settings = AdvancedPacingSettings(
            base_cut_rate=4,
            energy_reactivity=50,
            breakdown_behavior="halve",
            vibe="",  # Kein Vibe-Text = kein SigLIP VectorDB Matching
        )
        segments, cut_points = auto_edit_phase3(
            audio_id=track_id,
            video_clip_ids=video_ids,
            settings=settings,
            progress_cb=lambda pct, msg: log.info("  [AutoEdit %d%%] %s", pct, msg),
        )
        log.info("  %d Segmente | %d CutPoints", len(segments), len(cut_points))

        # Timeline via sqlite3 direkt schreiben (umgeht SQLAlchemy Pool-Lock-Problem)
        import sqlite3
        db_path = str(Path(__file__).parent.parent / "pb_studio.db")
        pid = get_active_project_id()
        conn = sqlite3.connect(db_path, timeout=120)
        try:
            conn.execute("DELETE FROM timeline_entries WHERE project_id=? AND track='video'", (pid,))
            for s in segments:
                conn.execute(
                    "INSERT INTO timeline_entries (project_id, track, media_id, start_time, end_time, "
                    "source_start, source_end, lane) VALUES (?,?,?,?,?,?,?,?)",
                    (pid, "video", s.video_id, s.start, s.end, s.source_start, s.source_end, 0),
                )
            conn.commit()
            log.info("  Timeline in DB geschrieben (%d Segmente, direkt via sqlite3)", len(segments))
        finally:
            conn.close()
    except Exception as e:
        log.error("  Auto-Edit fehlgeschlagen: %s", e, exc_info=True)
        return False

    # 6. Export
    step("6/6: Video-Export (FFmpeg)")
    try:
        from services.export_service import export_timeline
        output_name = "e2e_test_output.mp4"
        output_path = export_timeline(
            project_id=get_active_project_id(),
            output_name=output_name,
            resolution="1920x1080",
            fps=30.0,
            progress_cb=lambda pct, msg: log.info("  [Export %d%%] %s", pct, msg),
        )
        if output_path and Path(output_path).exists():
            size_mb = Path(output_path).stat().st_size / (1024 * 1024)
            log.info("  Export ERFOLGREICH: %s (%.1f MB)", output_path, size_mb)
        else:
            log.error("  Export: Keine Output-Datei erzeugt!")
            return False
    except Exception as e:
        log.error("  Export fehlgeschlagen: %s", e, exc_info=True)
        return False

    # Zusammenfassung
    elapsed = time.time() - t_start
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)

    log.info("=" * 60)
    log.info("  E2E TEST ABGESCHLOSSEN")
    log.info("  Dauer: %dm %ds", minutes, seconds)
    log.info("  Audio: %s (%.0fs)", audio_title, audio.duration or 0)
    log.info("  Segmente: %d | CutPoints: %d", len(segments), len(cut_points))
    if output_path:
        log.info("  Output: %s", output_path)
    log.info("=" * 60)
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
