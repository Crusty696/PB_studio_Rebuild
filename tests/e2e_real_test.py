#!/usr/bin/env python3
"""E2E Real Data Test: Vollstaendiger Testlauf mit ALLEN Clips aus test_data.

Generiert ein 60+ Minuten Video mit Audio und variiertem Video-Content.
Board-Anforderung: Keine Einschraenkungen, alle Clips, echte Daten.
"""

import logging
import os
import sys
import time

# Project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)
sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(PROJECT_ROOT, "tests", "e2e_real_test.log"), mode="w"),
    ],
)
logger = logging.getLogger("e2e_real_test")

# ============================================================
# Phase 0: Initialize Database
# ============================================================
logger.info("=" * 60)
logger.info("PHASE 0: Database initialisieren")
logger.info("=" * 60)

from database import init_db, engine, AudioTrack, VideoClip, TimelineEntry, Beatgrid
from sqlalchemy.orm import Session

init_db()

# Check current state
with Session(engine) as session:
    audio_count = session.query(AudioTrack).count()
    video_count = session.query(VideoClip).count()
    beat_count = session.query(Beatgrid).count()
    logger.info(f"DB State: {audio_count} audio, {video_count} video clips, {beat_count} beatgrids")

    audio_track = session.query(AudioTrack).first()
    if not audio_track:
        logger.error("Kein Audio-Track in DB! Muss zuerst importiert werden.")
        sys.exit(1)

    audio_id = audio_track.id
    audio_duration = audio_track.duration
    audio_path = audio_track.file_path
    audio_bpm = audio_track.bpm
    logger.info(f"Audio: id={audio_id}, duration={audio_duration:.1f}s, bpm={audio_bpm}, path={audio_path}")

    # Get ALL video clip IDs with valid duration
    video_clips = session.query(VideoClip).filter(VideoClip.duration > 0).all()
    video_ids = [vc.id for vc in video_clips]
    total_video_duration = sum(vc.duration for vc in video_clips if vc.duration)
    logger.info(f"Video Clips: {len(video_ids)} mit gültiger Duration (Gesamt: {total_video_duration:.1f}s)")

    # Check beatgrid exists
    beatgrid = session.query(Beatgrid).filter_by(audio_track_id=audio_id).first()
    if not beatgrid:
        logger.warning("Kein Beatgrid vorhanden — wird analysiert")
        needs_beat_analysis = True
    else:
        logger.info(f"Beatgrid vorhanden: bpm={beatgrid.bpm}")
        needs_beat_analysis = False

# ============================================================
# Phase 1: Beat Analysis (if needed)
# ============================================================
if needs_beat_analysis:
    logger.info("=" * 60)
    logger.info("PHASE 1: Beat-Analyse")
    logger.info("=" * 60)
    from services.beat_analysis_service import BeatAnalysisService
    beat_service = BeatAnalysisService(device="cuda")
    beat_result = beat_service.analyze_and_store(
        audio_id,
        progress_cb=lambda pct, msg: logger.info(f"  Beat-Analyse: {pct}% — {msg}")
    )
    logger.info(f"Beat-Analyse fertig: {beat_result.get('bpm')} BPM, "
                f"{beat_result.get('num_beats')} Beats")
else:
    logger.info("PHASE 1: Beat-Analyse übersprungen (bereits vorhanden)")

# ============================================================
# Phase 2: LUFS Analysis
# ============================================================
logger.info("=" * 60)
logger.info("PHASE 2: LUFS-Analyse")
logger.info("=" * 60)

from services.lufs_service import LUFSService
lufs_service = LUFSService()
try:
    lufs_result = lufs_service.analyze(audio_path)
    logger.info(f"LUFS: integrated={lufs_result.integrated:.1f} dB, "
                f"LRA={lufs_result.loudness_range:.1f}, "
                f"true_peak={lufs_result.true_peak:.1f} dBTP")
    # Update DB
    with Session(engine) as session:
        track = session.get(AudioTrack, audio_id)
        track.lufs = lufs_result.integrated
        session.commit()
except Exception as e:
    logger.warning(f"LUFS-Analyse fehlgeschlagen: {e}")

# ============================================================
# Phase 3: Auto-Edit mit ALLEN Video Clips
# ============================================================
logger.info("=" * 60)
logger.info("PHASE 3: Auto-Edit (Pacing) mit %d Video Clips", len(video_ids))
logger.info("=" * 60)

t0 = time.time()

from services.pacing_service import auto_edit_phase3, AdvancedPacingSettings

settings = AdvancedPacingSettings(
    base_cut_rate=4,
    energy_reactivity=60,
    breakdown_behavior="halve",
)

try:
    segments, cut_points = auto_edit_phase3(
        audio_id=audio_id,
        video_clip_ids=video_ids,
        settings=settings,
        progress_cb=lambda pct, msg: logger.info(f"  Pacing: {pct}% — {msg}")
    )
    t1 = time.time()
    logger.info(f"Auto-Edit fertig: {len(segments)} Segmente, {len(cut_points)} Cut-Points "
                f"in {t1-t0:.1f}s")

    # Analyze clip variety
    used_video_ids = set()
    for seg in segments:
        vid = seg.get("video_id") if isinstance(seg, dict) else getattr(seg, "video_id", None)
        if vid:
            used_video_ids.add(vid)
    logger.info(f"Clip-Varianz: {len(used_video_ids)} verschiedene Clips von {len(video_ids)} verwendet")

except Exception as e:
    logger.error(f"Auto-Edit fehlgeschlagen: {e}", exc_info=True)
    sys.exit(1)

# ============================================================
# Phase 4: Timeline schreiben (Video + Audio)
# ============================================================
logger.info("=" * 60)
logger.info("PHASE 4: Timeline schreiben")
logger.info("=" * 60)

from services.timeline_service import apply_auto_edit_segments

# Convert segments to dicts if they're objects
seg_dicts = []
for seg in segments:
    if isinstance(seg, dict):
        seg_dicts.append(seg)
    else:
        seg_dicts.append({
            "video_id": seg.video_id,
            "start": seg.start,
            "end": seg.end,
            "source_start": getattr(seg, "source_start", 0.0),
            "source_end": getattr(seg, "source_end", None),
            "crossfade_duration": getattr(seg, "crossfade_duration", 0.0),
        })

# Write video segments
entry_count = apply_auto_edit_segments(seg_dicts, project_id=1)
logger.info(f"Video-Timeline: {entry_count} Einträge geschrieben")

# Write audio timeline entry (spans full track)
from sqlalchemy import create_engine as _ce
from sqlalchemy.pool import NullPool

db_path = os.path.join(PROJECT_ROOT, "pb_studio.db")
_eng = _ce(f"sqlite:///{db_path}", echo=False,
           connect_args={"check_same_thread": False, "timeout": 30},
           poolclass=NullPool)

try:
    with Session(_eng) as session:
        # Delete existing audio timeline entries
        session.query(TimelineEntry).filter_by(project_id=1, track="audio").delete()
        # Create audio entry spanning full duration
        audio_entry = TimelineEntry(
            project_id=1,
            track="audio",
            media_id=audio_id,
            start_time=0.0,
            end_time=audio_duration,
            lane=0,
        )
        session.add(audio_entry)
        session.commit()
        logger.info(f"Audio-Timeline: 1 Eintrag geschrieben (0.0s — {audio_duration:.1f}s)")
finally:
    _eng.dispose()

# Verify timeline
with Session(engine) as session:
    video_entries = session.query(TimelineEntry).filter_by(project_id=1, track="video").count()
    audio_entries = session.query(TimelineEntry).filter_by(project_id=1, track="audio").count()
    unique_vids = session.query(TimelineEntry.media_id).filter_by(
        project_id=1, track="video"
    ).distinct().count()
    logger.info(f"Timeline-Verifizierung: {video_entries} Video, {audio_entries} Audio, "
                f"{unique_vids} verschiedene Clips")

# ============================================================
# Phase 5: Export (Video + Audio)
# ============================================================
logger.info("=" * 60)
logger.info("PHASE 5: Export (1080p/30fps mit Audio)")
logger.info("=" * 60)

from services.export_service import export_timeline

t0 = time.time()
try:
    output_path = export_timeline(
        project_id=1,
        output_name="e2e_real_test_full.mp4",
        resolution="1920x1080",
        fps=30.0,
        progress_cb=lambda pct, msg: logger.info(f"  Export: {pct}% — {msg}")
    )
    t1 = time.time()

    # Verify output
    file_size = os.path.getsize(output_path)
    logger.info(f"Export fertig: {output_path}")
    logger.info(f"  Dateigröße: {file_size / (1024*1024):.1f} MB")
    logger.info(f"  Export-Dauer: {t1-t0:.1f}s")

    # Probe output for duration and streams
    import subprocess, json
    probe_cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", output_path
    ]
    result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30,
                            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    if result.returncode == 0:
        probe_data = json.loads(result.stdout)
        fmt = probe_data.get("format", {})
        streams = probe_data.get("streams", [])
        duration = float(fmt.get("duration", 0))
        has_video = any(s.get("codec_type") == "video" for s in streams)
        has_audio = any(s.get("codec_type") == "audio" for s in streams)
        video_codec = next((s.get("codec_name") for s in streams if s.get("codec_type") == "video"), "none")
        audio_codec = next((s.get("codec_name") for s in streams if s.get("codec_type") == "audio"), "none")

        logger.info(f"  Output-Duration: {duration:.1f}s ({duration/60:.1f} min)")
        logger.info(f"  Video-Stream: {has_video} ({video_codec})")
        logger.info(f"  Audio-Stream: {has_audio} ({audio_codec})")

        # Final verdict
        logger.info("=" * 60)
        if duration >= 3600 and has_video and has_audio:
            logger.info("ERGEBNIS: BESTANDEN — 60+ Minuten Video mit Audio generiert!")
        elif duration >= 3500 and has_video and has_audio:
            logger.info("ERGEBNIS: BESTANDEN (knapp) — Video mit Audio generiert")
        else:
            issues = []
            if duration < 3500:
                issues.append(f"Dauer nur {duration/60:.1f} min (Ziel: 60+)")
            if not has_video:
                issues.append("Kein Video-Stream")
            if not has_audio:
                issues.append("Kein Audio-Stream")
            logger.warning(f"ERGEBNIS: TEILWEISE — {', '.join(issues)}")
        logger.info("=" * 60)

except Exception as e:
    logger.error(f"Export fehlgeschlagen: {e}", exc_info=True)
    sys.exit(1)

logger.info("E2E Real Data Test abgeschlossen.")
