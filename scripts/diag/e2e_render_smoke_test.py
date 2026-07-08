import os
import sys
import time
import logging
from pathlib import Path

# Setup Path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# Setup Env Variables
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
)
logger = logging.getLogger("e2e_render_smoke_test")

# 1. DB initialisieren (E2E-Projekt-Verzeichnis nutzen, um produktive DBs nicht zu stoeren)
from database.session import set_project
E2E_PROJECT_ROOT = PROJECT_ROOT / "test-report" / "e2e-render-smoke-project"
E2E_PROJECT_ROOT.mkdir(parents=True, exist_ok=True)
set_project(E2E_PROJECT_ROOT)

from database import init_db, engine, Session, Project, AudioTrack, VideoClip
init_db()

with Session(engine) as s:
    project = s.query(Project).filter_by(id=1).first()
    if not project:
        s.add(Project(
            id=1,
            name="E2E Render Smoke Test",
            path=str(E2E_PROJECT_ROOT),
            resolution="854x480",
            fps=30.0,
        ))
        s.commit()

# 2. Test-Materialien definieren
audio_path = r"C:/Users/David_Lochmann/Music/Crusty Progressive Psy Set2.mp3"
video_dir = Path(r"C:/Users/David_Lochmann/Videos/Solo_Natur-20260406T220640Z-3-001/Solo_Natur")

# 3. Audio-Datei importieren und analysieren
logger.info("Importiere Audio...")
from services.ingest_service import ingest_audio
audio_track = ingest_audio(audio_path)
audio_id = audio_track.id
logger.info(f"Audio importiert mit ID={audio_id}")

logger.info("Fuehre Beat-Analyse aus...")
from services.beat_analysis_service import BeatAnalysisService
BeatAnalysisService().analyze_and_store(audio_id)

logger.info("Fuehre Waveform-Analyse aus...")
from services.ai_audio_service import FrequencyAnalyzer
FrequencyAnalyzer().analyze_and_store(audio_id)

logger.info("Fuehre Key-Erkennung aus...")
from services.key_detection_service import KeyDetectionService
KeyDetectionService().detect_key(audio_track.file_path)

logger.info("Fuehre LUFS-Analyse aus...")
from services.lufs_service import LUFSService
LUFSService().analyze(audio_track.file_path)

logger.info("Fuehre Struktur-Erkennung aus...")
from services.structure_detection_service import StructureDetectionService
StructureDetectionService().detect(audio_track.file_path, bpm=audio_track.bpm)

logger.info("Fuehre Demucs Stem-Separation aus...")
from services.ai_audio_service import StemSeparator
StemSeparator().separate_and_store(audio_id)

# 4. Videos importieren und analysieren
video_clips = []
video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
logger.info(f"Suche Videos in {video_dir}...")
video_files = [f for f in video_dir.iterdir() if f.suffix.lower() in video_exts]

from services.ingest_service import ingest_video
from services.video_analysis_service import run_full_pipeline

for vf in video_files[:5]:  # Wir nehmen die ersten 5 Videos fuer den Smoke-Test
    logger.info(f"Importiere Video {vf.name}...")
    clip = ingest_video(str(vf))
    video_clips.append(clip)
    logger.info(f"Video {vf.name} importiert mit ID={clip.id}")
    logger.info(f"Fuehre Video-Pipeline fuer {vf.name} aus...")
    run_full_pipeline(video_path=clip.file_path, video_clip_id=clip.id)

# 5. Auto-Edit ausfuehren und in DB eintragen
logger.info("Fuehre Auto-Edit aus...")
from services.pacing_service import auto_edit_phase3, AdvancedPacingSettings
from services.timeline_service import apply_auto_edit_segments

settings = AdvancedPacingSettings(
    base_cut_rate=4,
    energy_reactivity=50.0,
    breakdown_behavior="halve",
    vibe="energetic",
    manual_density_curve=None,
    anchors=[],
)

video_ids = [c.id for c in video_clips]
segments, cut_points = auto_edit_phase3(
    audio_id=audio_id,
    video_ids=video_ids,
    settings=settings,
)

logger.info(f"Auto-Edit erzeugt: {len(segments)} Segmente.")
# Segmente serialisieren
seg_dicts = [
    {
        "video_id": s.video_id, "video_path": s.video_path,
        "start": s.start, "end": s.end,
        "source_start": s.source_start, "source_end": s.source_end,
        "is_anchor": s.is_anchor, "scene_id": s.scene_id,
        "crossfade": s.crossfade_duration, "section_type": s.section_type,
    }
    for s in segments
]

# In Timeline DB eintragen
apply_auto_edit_segments(seg_dicts, project_id=1)

# Audio-Eintrag hinzufügen
from database import TimelineEntry
with Session(engine) as s:
    audio_entry = TimelineEntry(
        project_id=1,
        track="audio",
        media_id=audio_id,
        start_time=0.0,
        end_time=audio_track.duration,
        source_start=0.0,
        source_end=audio_track.duration,
        lane=0,
    )
    s.add(audio_entry)
    s.commit()

# 6. Timeline exportieren
logger.info("Starte Export...")
from services.export_service import export_timeline

output_name = "e2e_smoke_output.mp4"
exports_dir = PROJECT_ROOT / "exports"
exports_dir.mkdir(parents=True, exist_ok=True)

output_path = export_timeline(
    project_id=1,
    output_name=output_name,
    resolution="854x480",
    fps=30.0,
)
logger.info(f"Export erfolgreich abgeschlossen. Datei: {output_path}")

# 7. Ergebnis-Video verifizieren
import subprocess
from services.startup_checks import get_ffprobe_bin
ffprobe = get_ffprobe_bin()
result = subprocess.run(
    [ffprobe, "-v", "quiet", "-show_entries", "format=duration",
     "-of", "csv=p=0", str(output_path)],
    capture_output=True, text=True, timeout=30,
    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
)
duration = float(result.stdout.strip())
file_size = Path(output_path).stat().st_size / (1024 * 1024)
logger.info(f"VERIFIKATION: Dauer={duration:.2f}s, Groesse={file_size:.1f}MB")

if duration > 0 and file_size > 0:
    logger.info("VERIFIKATION ERFOLGREICH (GREEN)")
    sys.exit(0)
else:
    logger.error("VERIFIKATION FEHLGESCHLAGEN (RED)")
    sys.exit(1)
