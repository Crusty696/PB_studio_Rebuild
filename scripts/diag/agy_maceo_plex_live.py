"""Autonomer E2E-Live-Test mit echten User-Dateien:
- Audio: Maceo Plex - Sub-Alot (free download).mp3
- Videos: Solo_Natur MP4s
- Struktur-Erkennung: StructureDetectionService

Schreibt in die konfigurierte PB-Studio-Datenbank und legt/benutzt dort das
Projekt ``MaceoPlex_LiveTest``. Nur bewusst als manuellen Live-Test starten.
"""
import os
import sys
import time
import logging
from pathlib import Path
from sqlalchemy.orm import Session

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("maceo_plex_live_test")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Paths
MACEO_AUDIO = r"C:\Users\David_Lochmann\Music\Maceo Plex - Sub-Alot (free download).mp3"
VIDEO_DIR = r"C:\Users\David_Lochmann\Videos\Solo_Natur-20260406T220640Z-3-001\Solo_Natur"

from database import engine, nullpool_session, Project, AudioTrack, VideoClip, Beatgrid, StructureSegment
from database.migrations import init_db
from services.ingest_service import ingest_audio, ingest_video
from services.beat_analysis_service import BeatAnalysisService
from services.structure_detection_service import StructureDetectionService

def run():
    print("============================================================")
    print("  AUTONOMER LIVE-TEST: MACEO PLEX (BEAT + STRUKTUR) & SOLO NATUR")
    print("============================================================")
    
    # 1. DB Init & Setup
    init_db()
    with nullpool_session() as db:
        # Create test project
        proj = db.query(Project).filter(Project.name == "MaceoPlex_LiveTest").first()
        if not proj:
            proj_path = str(PROJECT_ROOT / "projects" / "MaceoPlex_LiveTest.pbproj")
            proj = Project(name="MaceoPlex_LiveTest", path=proj_path, fps=30.0)
            db.add(proj)
            db.commit()
            db.refresh(proj)
        proj_id = proj.id
        print(f"[1/6] Test-Projekt 'MaceoPlex_LiveTest' bereit (ID: {proj_id})")

    # 2. Ingest Maceo Plex track
    print(f"[2/6] Ingesting Maceo Plex Audio: {MACEO_AUDIO}")
    audio_track = ingest_audio(MACEO_AUDIO, project_id=proj_id)
    with nullpool_session() as db:
        if audio_track is None:
            audio_track = db.query(AudioTrack).filter(AudioTrack.project_id == proj_id, AudioTrack.file_path == str(Path(MACEO_AUDIO).resolve())).first()
        assert audio_track is not None, "ingest_audio failed for Maceo Plex"
        audio_id = audio_track.id
        audio_dur = audio_track.duration
        audio_sr = audio_track.sample_rate
    print(f"      Audio-Track ID: {audio_id}, Dauer: {audio_dur:.2f}s, SR: {audio_sr}")

    # 3. Ingest Videos
    videos = [f for f in os.listdir(VIDEO_DIR) if f.endswith(".mp4")][:3]
    ingested_vids_count = 0
    for vname in videos:
        vpath = os.path.join(VIDEO_DIR, vname)
        vclip = ingest_video(vpath, project_id=proj_id)
        ingested_vids_count += 1
    print(f"[3/6] {ingested_vids_count} Videos in Projekt {proj_id} importiert.")

    # 4. Beat Analysis
    print(f"[4/6] Starte Beat-Analyse fuer Maceo Plex (Track ID: {audio_id})...")
    beat_svc = BeatAnalysisService()
    t0 = time.time()
    result = beat_svc.analyze_and_store(audio_id)
    t_elapsed = time.time() - t0
    print(f"      Beat-Analyse abgeschlossen in {t_elapsed:.2f}s!")

    # 5. Structure Detection
    print(f"[5/6] Starte Struktur-Erkennung (Intro/Verse/Buildup/Drop/Outro) fuer Maceo Plex...")
    struct_svc = StructureDetectionService()
    t1 = time.time()
    with nullpool_session() as db:
        bg = db.query(Beatgrid).filter(Beatgrid.audio_track_id == audio_id).first()
        bpm_val = bg.bpm if bg else None
    
    struct_res = struct_svc.detect(MACEO_AUDIO, bpm=bpm_val)
    struct_svc.save_to_db(audio_id, struct_res)
    t1_elapsed = time.time() - t1
    print(f"      Struktur-Erkennung abgeschlossen in {t1_elapsed:.2f}s!")

    # 6. DB Verification
    with nullpool_session() as db:
        bg = db.query(Beatgrid).filter(Beatgrid.audio_track_id == audio_id).first()
        segs = db.query(StructureSegment).filter(StructureSegment.audio_track_id == audio_id).order_by(StructureSegment.start_time).all()
        print("============================================================")
        print("  VERIFIKATIONSERGEBNIS:")
        print(f"  - BeatGrid BPM: {bg.bpm if bg else 'N/A'}")
        print(f"  - BeatGrid Groove Template: {bg.groove_template if bg else 'N/A'}")
        print(f"  - BeatGrid Syncopation Score: {bg.syncopation_score if bg else 'N/A'}")
        print(f"  - Beats Count: {len(bg.beat_positions) if (bg and bg.beat_positions) else 0}")
        print(f"  - Struktur-Genre: {struct_res.detected_genre} (Conf: {struct_res.genre_confidence:.2f})")
        print(f"  - Struktur-Segmente ({len(segs)} Total):")
        for s in segs:
            print(f"      * {s.label.upper()}: {s.start_time:.1f}s - {s.end_time:.1f}s (Dauer: {s.end_time - s.start_time:.1f}s, Energy: {s.energy:.2f})")
        print("============================================================")
        assert bg is not None, "Beatgrid not created!"
        assert len(segs) > 0, "No structure segments detected!"
        print("  AUTONOMER LIVE-TEST STATUS: 100% SUCCESS / VERIFIED")

if __name__ == "__main__":
    run()
