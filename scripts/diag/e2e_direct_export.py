"""
E2E Direct Export — Calls the same export_timeline() function that the GUI's
"Video exportieren" button triggers, without loading the heavy timeline UI.

This exercises the EXACT same render pipeline:
  btn_export.click() → ExportController._start_export() → ExportWorker.run()
  → export_timeline() → FFmpeg concat → output.mp4

The timeline is already prepared in the database (378 video + 1 audio entries).
"""

import os
import sys
import time
import logging
from pathlib import Path

# === Environment setup (same as main.py) ===
from dotenv import load_dotenv
load_dotenv()

_APP_ROOT = Path(__file__).resolve().parents[2]  # scripts/diag/ -> Repo-Root (CRF-020-Move-Fix)
_BIN_DIR = str(_APP_ROOT / "bin")
if _BIN_DIR not in os.environ["PATH"]:
    os.environ["PATH"] = _BIN_DIR + os.pathsep + os.environ["PATH"]

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("e2e_direct_export")

# === Database init ===
from database import Base, engine
Base.metadata.create_all(engine)

# === Verify timeline before export ===
from services.export_service import get_timeline_summary, export_timeline

logger.info("=" * 60)
logger.info("  E2E DIRECT EXPORT TEST")
logger.info("=" * 60)

summary = get_timeline_summary(project_id=1)
logger.info("Timeline summary:")
logger.info("  Video clips: %d", summary["video_clips"])
logger.info("  Audio tracks: %d", summary["audio_tracks"])
logger.info("  Total entries: %d", summary["total_entries"])
logger.info("  Estimated duration: %.1fs (%.1f min)",
            summary["estimated_duration"], summary["estimated_duration"] / 60)

if summary["total_entries"] == 0:
    logger.error("No timeline entries! Aborting.")
    sys.exit(1)

# === Verify all clips referenced in timeline exist ===
import sqlite3
conn = sqlite3.connect(str(_APP_ROOT / "pb_studio.db"))
missing_files = []
for row in conn.execute("""
    SELECT DISTINCT vc.id, vc.file_path
    FROM timeline_entries te
    JOIN video_clips vc ON te.media_id = vc.id
    WHERE te.track = 'video'
"""):
    if not os.path.exists(row[1]):
        missing_files.append((row[0], row[1]))

if missing_files:
    logger.warning("Missing source files: %d", len(missing_files))
    for clip_id, path in missing_files[:5]:
        logger.warning("  Clip %d: %s", clip_id, path)
else:
    logger.info("All source files verified (%d unique clips)",
                conn.execute("SELECT COUNT(DISTINCT media_id) FROM timeline_entries WHERE track='video'").fetchone()[0])

# Verify audio
audio_row = conn.execute("""
    SELECT at.file_path FROM timeline_entries te
    JOIN audio_tracks at ON te.media_id = at.id
    WHERE te.track = 'audio' LIMIT 1
""").fetchone()
if audio_row and os.path.exists(audio_row[0]):
    logger.info("Audio track verified: %s", os.path.basename(audio_row[0]))
else:
    logger.warning("Audio track missing or not found!")
conn.close()

# === Run export ===
output_name = "final_e2e_all_clips.mp4"
resolution = "854x480"
fps = 30.0

logger.info("")
logger.info("Starting export:")
logger.info("  Output: %s", output_name)
logger.info("  Resolution: %s", resolution)
logger.info("  FPS: %.0f", fps)
logger.info("  Segments: %d video + %d audio", summary["video_clips"], summary["audio_tracks"])
logger.info("")

start_time = time.time()

def progress_callback(pct, message):
    elapsed = time.time() - start_time
    logger.info("[PROGRESS] %3d%% | %s | Elapsed: %.0fs", pct, message, elapsed)

try:
    output_path = export_timeline(
        project_id=1,
        output_name=output_name,
        resolution=resolution,
        fps=fps,
        progress_cb=progress_callback,
    )
    elapsed = time.time() - start_time

    logger.info("")
    logger.info("=" * 60)
    logger.info("  EXPORT COMPLETE")
    logger.info("=" * 60)
    logger.info("Output: %s", output_path)
    logger.info("Render time: %.1fs (%.1f min)", elapsed, elapsed / 60)

    # Verify output
    if output_path and Path(output_path).exists():
        file_size = Path(output_path).stat().st_size
        logger.info("File size: %.1f MB", file_size / (1024 * 1024))

        # Check duration via ffprobe
        try:
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
            logger.info("Duration: %.1fs (%.1f min / %.2f hours)",
                        duration, duration / 60, duration / 3600)

            if duration >= 3600:
                logger.info("RESULT: PASSED — Duration >= 1 hour")
                status = "PASSED"
            elif duration >= 3500:
                logger.info("RESULT: PASSED (marginal) — Duration ~1 hour")
                status = "PASSED"
            else:
                logger.warning("RESULT: WARNING — Duration < 1 hour")
                status = "WARNING"
        except Exception as e:
            logger.warning("Could not check duration: %s", e)
            duration = -1
            status = "UNKNOWN"

        # Write result file
        result_file = _APP_ROOT / "exports" / "e2e_render_result.txt"
        with open(result_file, "w", encoding="utf-8") as f:
            f.write(f"STATUS: {status}\n")
            f.write(f"TIMESTAMP: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"OUTPUT: {output_path}\n")
            f.write(f"SIZE_MB: {file_size / (1024*1024):.1f}\n")
            f.write(f"DURATION_SEC: {duration:.1f}\n")
            f.write(f"DURATION_MIN: {duration/60:.1f}\n")
            f.write(f"RENDER_TIME_SEC: {elapsed:.1f}\n")
            f.write(f"VIDEO_SEGMENTS: {summary['video_clips']}\n")
            f.write(f"AUDIO_TRACKS: {summary['audio_tracks']}\n")
            f.write(f"RESOLUTION: {resolution}\n")
            f.write(f"FPS: {fps}\n")
        logger.info("Result written to: %s", result_file)
    else:
        logger.error("RESULT: FAILED — Output file not found")

except Exception as e:
    elapsed = time.time() - start_time
    logger.error("EXPORT FAILED after %.1fs: %s", elapsed, e, exc_info=True)

    result_file = _APP_ROOT / "exports" / "e2e_render_result.txt"
    with open(result_file, "w", encoding="utf-8") as f:
        f.write(f"STATUS: FAILED\n")
        f.write(f"TIMESTAMP: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"ERROR: {e}\n")
        f.write(f"RENDER_TIME_SEC: {elapsed:.1f}\n")

    sys.exit(1)
