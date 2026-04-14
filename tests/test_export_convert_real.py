"""Funktionstest: Export- und Convert-Services mit echten Videodaten.

Testet jeden Service einzeln, faengt Crashes ab und berichtet.
Verwendet eine temporaere Datenbank und temporaere Output-Verzeichnisse.
"""
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

# ---- Setup: Project root auf sys.path ----
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
BIN_DIR = PROJECT_ROOT / "bin"

# FFmpeg/FFprobe ins PATH eintragen
os.environ["PATH"] = str(BIN_DIR) + os.pathsep + os.environ.get("PATH", "")

# Logging einrichten
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("TEST_EXPORT_CONVERT")

# ---- Echte Videodatei ----
VIDEO_PATH = r"C:\Users\David Lochmann\Documents\Solo_Natur-20260406T220640Z-3-001\Solo_Natur\20250612_2128_Neon_Jungle_Dreamscape_v1.mp4"
FFPROBE = str(BIN_DIR / "ffprobe.exe")

# ---- Ergebnis-Sammlung ----
RESULTS = []

def record(name, status, duration_sec, details="", output_file=None, output_size=None, video_props=None):
    entry = {
        "test": name,
        "status": status,
        "duration_sec": round(duration_sec, 2),
        "details": details,
    }
    if output_file:
        entry["output_file"] = str(output_file)
    if output_size is not None:
        entry["output_size_mb"] = round(output_size / (1024*1024), 2)
    if video_props:
        entry["video_props"] = video_props
    RESULTS.append(entry)
    icon = "PASS" if status == "PASS" else "FAIL" if status == "FAIL" else "CRASH"
    print(f"\n{'='*60}")
    print(f"  [{icon}] {name}  ({entry['duration_sec']}s)")
    if details:
        print(f"  Details: {details}")
    if output_file:
        print(f"  Output: {output_file}")
    if output_size is not None:
        print(f"  Size: {entry['output_size_mb']} MB")
    if video_props:
        print(f"  Video: {video_props}")
    print(f"{'='*60}")


def probe_output(file_path):
    """Probe output video for resolution, codec, duration."""
    try:
        cmd = [
            FFPROBE, "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,codec_name",
            "-of", "json",
            str(file_path),
        ]
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                                encoding="utf-8", errors="replace", **kwargs)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            streams = data.get("streams", [])
            if streams:
                s = streams[0]
                rfr = s.get("r_frame_rate", "0/1")
                if "/" in rfr:
                    num, den = rfr.split("/")
                    fps = float(num) / float(den) if float(den) > 0 else 0.0
                else:
                    fps = float(rfr)
                return {
                    "width": s.get("width", 0),
                    "height": s.get("height", 0),
                    "fps": round(fps, 2),
                    "codec": s.get("codec_name", ""),
                }
    except Exception as e:
        logger.warning("Probe fehlgeschlagen: %s", e)
    return None


# ====================================================================
#  TEMPORAERE DATENBANK + PROJECT SETUP
# ====================================================================
print("\n" + "=" * 70)
print("  PB STUDIO — EXPORT/CONVERT FUNKTIONSTEST MIT ECHTEN DATEN")
print("=" * 70)

# Erstelle temporaeres Projektverzeichnis fuer DB + Exports
TEMP_PROJECT = Path(tempfile.mkdtemp(prefix="pb_test_project_"))
print(f"\nTemp-Projektverzeichnis: {TEMP_PROJECT}")

# Patch APP_ROOT BEVOR database-Module geladen werden
# Wir muessen session.APP_ROOT und die engine auf das temp-Verzeichnis setzen
import database.session as db_session
original_app_root = db_session.APP_ROOT

# Patche APP_ROOT auf temp dir
db_session.APP_ROOT = TEMP_PROJECT

# Erstelle eine neue Engine fuer die temp DB
temp_db_path = TEMP_PROJECT / "pb_studio.db"
new_engine = db_session._make_engine(temp_db_path)
db_session.engine.swap(new_engine)

print(f"Temp-Datenbank: {temp_db_path}")

# Jetzt erst die Models und init_db laden
from database.models import Base, Project, VideoClip, TimelineEntry
from database import engine, init_db
from sqlalchemy.orm import Session

# Schema erstellen (ohne Alembic Migrations — nur create_all)
Base.metadata.create_all(engine)
print("DB-Schema erstellt (create_all)")

# Projekt + VideoClip anlegen
with Session(engine) as session:
    project = Project(
        name="Test-Projekt",
        path=str(TEMP_PROJECT),
        resolution="1920x1080",
        fps=30.0,
    )
    session.add(project)
    session.commit()
    PROJECT_ID = project.id
    print(f"Projekt angelegt: id={PROJECT_ID}")

    # VideoClip anlegen
    clip = VideoClip(
        project_id=PROJECT_ID,
        file_path=VIDEO_PATH,
        duration=10.0,  # wird spaeter ggf. korrigiert
        width=1920,
        height=1080,
        fps=30.0,
        codec="h264",
    )
    session.add(clip)
    session.commit()
    CLIP_ID = clip.id
    print(f"VideoClip angelegt: id={CLIP_ID}")

    # Timeline-Entry: 1 Clip, 0-5s
    entry = TimelineEntry(
        project_id=PROJECT_ID,
        track="video",
        media_id=CLIP_ID,
        start_time=0.0,
        end_time=5.0,
        source_start=0.0,
        source_end=5.0,
        lane=0,
        crossfade_duration=0.0,
        brightness=0.0,
        contrast=1.0,
    )
    session.add(entry)
    session.commit()
    print(f"TimelineEntry angelegt: 0-5s")

print(f"\nSetup abgeschlossen. Starte Tests...\n")


# ====================================================================
#  TEST 1: detect_nvenc()
# ====================================================================
print("\n--- TEST 1: detect_nvenc() ---")
t0 = time.perf_counter()
try:
    from services.convert_service import detect_nvenc
    result = detect_nvenc()
    dt = time.perf_counter() - t0
    details = f"h264_nvenc={result.get('h264_nvenc')}, hevc_nvenc={result.get('hevc_nvenc')}, cuda={result.get('cuda_hwaccel')}, ffmpeg={result.get('ffmpeg_version', '?')[:60]}"
    # GTX 1060 sollte NVENC unterstuetzen
    if result.get("h264_nvenc"):
        record("detect_nvenc()", "PASS", dt, details)
    else:
        record("detect_nvenc()", "FAIL", dt, f"h264_nvenc=False (erwartet True auf GTX 1060). {details}")
except Exception as e:
    dt = time.perf_counter() - t0
    record("detect_nvenc()", "CRASH", dt, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


# ====================================================================
#  TEST 2: get_available_presets()
# ====================================================================
print("\n--- TEST 2: get_available_presets() ---")
t0 = time.perf_counter()
try:
    from services.convert_service import get_available_presets
    presets = get_available_presets()
    dt = time.perf_counter() - t0
    names = [p["name"] for p in presets]
    expected = ["Edit-Proxy (540p)", "Master (1080p)", "DaVinci-Proxy (720p)"]
    all_found = all(n in names for n in expected)
    details = f"Presets: {names}, alle erwartet={all_found}"
    if all_found and len(presets) == 3:
        record("get_available_presets()", "PASS", dt, details)
    else:
        record("get_available_presets()", "FAIL", dt, f"Fehlende Presets. {details}")
except Exception as e:
    dt = time.perf_counter() - t0
    record("get_available_presets()", "CRASH", dt, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


# ====================================================================
#  TEST 3a: convert() — Edit-Proxy (540p)
# ====================================================================
print("\n--- TEST 3a: convert() — Edit-Proxy (540p) ---")
temp_convert_dir = Path(tempfile.mkdtemp(prefix="pb_test_convert_"))
t0 = time.perf_counter()
try:
    from services.convert_service import convert
    output_ep = temp_convert_dir / "test_edit_proxy.mp4"
    progress_msgs = []
    def cb_ep(pct, msg):
        progress_msgs.append((pct, msg))
    result_path = convert(VIDEO_PATH, "edit_proxy", output_path=str(output_ep), progress_cb=cb_ep)
    dt = time.perf_counter() - t0
    out_path = Path(result_path)
    if out_path.exists() and out_path.stat().st_size > 0:
        size = out_path.stat().st_size
        props = probe_output(out_path)
        details = f"Progress-Callbacks: {len(progress_msgs)}, letzte: {progress_msgs[-1] if progress_msgs else 'keine'}"
        record("convert(edit_proxy)", "PASS", dt, details, out_path, size, props)
    else:
        record("convert(edit_proxy)", "FAIL", dt, f"Ausgabedatei fehlt oder leer: {result_path}")
except Exception as e:
    dt = time.perf_counter() - t0
    record("convert(edit_proxy)", "CRASH", dt, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


# ====================================================================
#  TEST 3b: convert() — Master (1080p)
# ====================================================================
print("\n--- TEST 3b: convert() — Master (1080p) ---")
t0 = time.perf_counter()
try:
    output_master = temp_convert_dir / "test_master.mp4"
    progress_msgs_m = []
    def cb_m(pct, msg):
        progress_msgs_m.append((pct, msg))
    result_path = convert(VIDEO_PATH, "master", output_path=str(output_master), progress_cb=cb_m)
    dt = time.perf_counter() - t0
    out_path = Path(result_path)
    if out_path.exists() and out_path.stat().st_size > 0:
        size = out_path.stat().st_size
        props = probe_output(out_path)
        details = f"Progress-Callbacks: {len(progress_msgs_m)}"
        record("convert(master)", "PASS", dt, details, out_path, size, props)
    else:
        record("convert(master)", "FAIL", dt, f"Ausgabedatei fehlt oder leer: {result_path}")
except Exception as e:
    dt = time.perf_counter() - t0
    record("convert(master)", "CRASH", dt, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


# ====================================================================
#  TEST 3c: convert() — DaVinci-Proxy (720p DNxHR)
# ====================================================================
print("\n--- TEST 3c: convert() — DaVinci-Proxy (720p DNxHR) ---")
t0 = time.perf_counter()
try:
    output_dv = temp_convert_dir / "test_davinci.mxf"
    progress_msgs_d = []
    def cb_d(pct, msg):
        progress_msgs_d.append((pct, msg))
    result_path = convert(VIDEO_PATH, "davinci", output_path=str(output_dv), progress_cb=cb_d)
    dt = time.perf_counter() - t0
    out_path = Path(result_path)
    if out_path.exists() and out_path.stat().st_size > 0:
        size = out_path.stat().st_size
        props = probe_output(out_path)
        details = f"Progress-Callbacks: {len(progress_msgs_d)}"
        record("convert(davinci)", "PASS", dt, details, out_path, size, props)
    else:
        record("convert(davinci)", "FAIL", dt, f"Ausgabedatei fehlt oder leer: {result_path}")
except Exception as e:
    dt = time.perf_counter() - t0
    record("convert(davinci)", "CRASH", dt, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


# ====================================================================
#  TEST 3d: convert() — Ungültiges Preset (Fehlerbehandlung)
# ====================================================================
print("\n--- TEST 3d: convert() — Ungültiges Preset ---")
t0 = time.perf_counter()
try:
    from services.errors import ConversionError
    try:
        convert(VIDEO_PATH, "nonexistent_preset")
        dt = time.perf_counter() - t0
        record("convert(invalid_preset)", "FAIL", dt, "Haette ConversionError werfen muessen")
    except ConversionError as e:
        dt = time.perf_counter() - t0
        record("convert(invalid_preset)", "PASS", dt, f"ConversionError korrekt: {e}")
except Exception as e:
    dt = time.perf_counter() - t0
    record("convert(invalid_preset)", "CRASH", dt, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


# ====================================================================
#  TEST 3e: convert() — Nicht-existente Datei (Fehlerbehandlung)
# ====================================================================
print("\n--- TEST 3e: convert() — Nicht-existente Datei ---")
t0 = time.perf_counter()
try:
    try:
        convert(r"C:\nonexistent\file.mp4", "edit_proxy")
        dt = time.perf_counter() - t0
        record("convert(missing_file)", "FAIL", dt, "Haette FileNotFoundError werfen muessen")
    except FileNotFoundError as e:
        dt = time.perf_counter() - t0
        record("convert(missing_file)", "PASS", dt, f"FileNotFoundError korrekt: {e}")
except Exception as e:
    dt = time.perf_counter() - t0
    record("convert(missing_file)", "CRASH", dt, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


# ====================================================================
#  TEST 4: export_timeline()
# ====================================================================
print("\n--- TEST 4: export_timeline() ---")
t0 = time.perf_counter()
try:
    from services.export_service import export_timeline
    progress_msgs_ex = []
    def cb_ex(pct, msg):
        progress_msgs_ex.append((pct, msg))
    result_path = export_timeline(
        project_id=PROJECT_ID,
        output_name="test_export.mp4",
        resolution="1280x720",
        fps=30.0,
        progress_cb=cb_ex,
    )
    dt = time.perf_counter() - t0
    out_path = Path(result_path)
    if out_path.exists() and out_path.stat().st_size > 0:
        size = out_path.stat().st_size
        props = probe_output(out_path)
        details = f"Progress-Callbacks: {len(progress_msgs_ex)}"
        record("export_timeline()", "PASS", dt, details, out_path, size, props)
    else:
        record("export_timeline()", "FAIL", dt, f"Ausgabedatei fehlt oder leer: {result_path}")
except Exception as e:
    dt = time.perf_counter() - t0
    record("export_timeline()", "CRASH", dt, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


# ====================================================================
#  TEST 5: export_preview()
# ====================================================================
print("\n--- TEST 5: export_preview() ---")
t0 = time.perf_counter()
try:
    from services.export_service import export_preview
    progress_msgs_pv = []
    def cb_pv(pct, msg):
        progress_msgs_pv.append((pct, msg))
    result_path = export_preview(
        project_id=PROJECT_ID,
        resolution="1280x720",
        fps=30.0,
        duration_limit=5.0,
        progress_cb=cb_pv,
    )
    dt = time.perf_counter() - t0
    out_path = Path(result_path)
    if out_path.exists() and out_path.stat().st_size > 0:
        size = out_path.stat().st_size
        props = probe_output(out_path)
        details = f"Progress-Callbacks: {len(progress_msgs_pv)}"
        record("export_preview()", "PASS", dt, details, out_path, size, props)
    else:
        record("export_preview()", "FAIL", dt, f"Ausgabedatei fehlt oder leer: {result_path}")
except Exception as e:
    dt = time.perf_counter() - t0
    record("export_preview()", "CRASH", dt, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


# ====================================================================
#  TEST 6: estimate_render_time()
# ====================================================================
print("\n--- TEST 6: estimate_render_time() ---")
t0 = time.perf_counter()
try:
    from services.export_service import estimate_render_time
    est = estimate_render_time(project_id=PROJECT_ID, resolution="1920x1080", fps=30.0)
    dt = time.perf_counter() - t0
    details = (
        f"estimated_seconds={est.get('estimated_seconds')}, "
        f"label='{est.get('estimated_label')}', "
        f"total_duration={est.get('total_duration')}, "
        f"segment_count={est.get('segment_count')}, "
        f"has_effects={est.get('has_effects')}, "
        f"preset={est.get('preset_summary')}"
    )
    if est.get("estimated_seconds", 0) > 0 and est.get("segment_count", 0) > 0:
        record("estimate_render_time()", "PASS", dt, details)
    else:
        record("estimate_render_time()", "FAIL", dt, f"Unerwartete Werte: {details}")
except Exception as e:
    dt = time.perf_counter() - t0
    record("estimate_render_time()", "CRASH", dt, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


# ====================================================================
#  TEST 7: TimelineService (OTIO)
# ====================================================================
print("\n--- TEST 7: TimelineService ---")

# 7a: create_timeline + add_clip
print("\n--- TEST 7a: TimelineService.create_timeline + add_clip ---")
t0 = time.perf_counter()
try:
    from services.timeline_service import TimelineService
    ts = TimelineService(fps=30.0)
    tl = ts.create_timeline("Funktionstest-Timeline")
    vt = ts.get_video_track()
    clip_otio = ts.add_clip(
        track=vt,
        name="TestClip",
        media_path=VIDEO_PATH,
        source_start=0.0,
        source_duration=5.0,
        available_duration=10.0,
        metadata={"test": True},
    )
    dt = time.perf_counter() - t0
    all_clips = ts.get_all_clips()
    details = f"Timeline='{tl.name}', Clips={len(all_clips)}, Clip-Name='{clip_otio.name}'"
    if len(all_clips) == 1 and clip_otio.name == "TestClip":
        record("TimelineService.create+add_clip", "PASS", dt, details)
    else:
        record("TimelineService.create+add_clip", "FAIL", dt, details)
except Exception as e:
    dt = time.perf_counter() - t0
    record("TimelineService.create+add_clip", "CRASH", dt, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")

# 7b: add_marker + get_markers
print("\n--- TEST 7b: TimelineService.add_marker + get_markers ---")
t0 = time.perf_counter()
try:
    marker = ts.add_marker("Beat1", time=1.0, duration=0.0, color="RED",
                           metadata={"type": "beat", "bpm": 128})
    markers = ts.get_markers()
    dt = time.perf_counter() - t0
    details = f"Markers={len(markers)}, first={markers[0] if markers else 'none'}"
    if len(markers) == 1 and markers[0]["name"] == "Beat1":
        record("TimelineService.add_marker", "PASS", dt, details)
    else:
        record("TimelineService.add_marker", "FAIL", dt, details)
except Exception as e:
    dt = time.perf_counter() - t0
    record("TimelineService.add_marker", "CRASH", dt, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")

# 7c: save_otio + load_otio
print("\n--- TEST 7c: TimelineService.save_otio + load_otio ---")
t0 = time.perf_counter()
try:
    otio_path = TEMP_PROJECT / "test_timeline.otio"
    saved = ts.save_otio(otio_path)

    ts2 = TimelineService(fps=30.0)
    loaded = ts2.load_otio(otio_path)
    dt = time.perf_counter() - t0
    clips_after = ts2.get_all_clips()
    markers_after = ts2.get_markers()
    details = f"Saved to {saved}, loaded clips={len(clips_after)}, markers={len(markers_after)}"
    if len(clips_after) == 1 and len(markers_after) == 1:
        record("TimelineService.save+load_otio", "PASS", dt, details)
    else:
        record("TimelineService.save+load_otio", "FAIL", dt, details)
except Exception as e:
    dt = time.perf_counter() - t0
    record("TimelineService.save+load_otio", "CRASH", dt, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")

# 7d: get_duration
print("\n--- TEST 7d: TimelineService.get_duration ---")
t0 = time.perf_counter()
try:
    dur = ts.get_duration()
    dt = time.perf_counter() - t0
    details = f"Duration={dur}s (erwartet ~5.0s)"
    if 4.9 <= dur <= 5.1:
        record("TimelineService.get_duration", "PASS", dt, details)
    else:
        record("TimelineService.get_duration", "FAIL", dt, details)
except Exception as e:
    dt = time.perf_counter() - t0
    record("TimelineService.get_duration", "CRASH", dt, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")

# 7e: add_transition
print("\n--- TEST 7e: TimelineService.add_transition ---")
t0 = time.perf_counter()
try:
    # Zweiten Clip hinzufuegen fuer Transition
    clip2 = ts.add_clip(
        track=vt,
        name="TestClip2",
        media_path=VIDEO_PATH,
        source_start=5.0,
        source_duration=5.0,
        available_duration=10.0,
    )
    trans = ts.add_transition(track=vt, position=1, duration=1.0)
    dt = time.perf_counter() - t0
    all_items = list(vt)
    details = f"Track-Items: {len(all_items)}, Transition='{trans.name}'"
    if trans.name.startswith("Crossfade"):
        record("TimelineService.add_transition", "PASS", dt, details)
    else:
        record("TimelineService.add_transition", "FAIL", dt, details)
except Exception as e:
    dt = time.perf_counter() - t0
    record("TimelineService.add_transition", "CRASH", dt, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")

# 7f: export_edl
print("\n--- TEST 7f: TimelineService.export_edl ---")
t0 = time.perf_counter()
try:
    edl_path = TEMP_PROJECT / "test.edl"
    saved_edl = ts.export_edl(edl_path)
    dt = time.perf_counter() - t0
    edl_exists = Path(saved_edl).exists()
    edl_size = Path(saved_edl).stat().st_size if edl_exists else 0
    details = f"EDL-Pfad={saved_edl}, exists={edl_exists}, size={edl_size}"
    if edl_exists and edl_size > 0:
        record("TimelineService.export_edl", "PASS", dt, details)
    else:
        record("TimelineService.export_edl", "FAIL", dt, details)
except Exception as e:
    dt = time.perf_counter() - t0
    record("TimelineService.export_edl", "CRASH", dt, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")

# 7g: set_beatgrid_metadata + get_beatgrid_metadata
print("\n--- TEST 7g: TimelineService.beatgrid_metadata ---")
t0 = time.perf_counter()
try:
    ts.set_beatgrid_metadata([0.0, 0.5, 1.0, 1.5, 2.0], 120.0)
    bg = ts.get_beatgrid_metadata()
    dt = time.perf_counter() - t0
    bpm = bg.get("bpm", 0)
    beats = bg.get("beat_positions", [])
    details = f"BPM={bpm}, beat_positions={beats}"
    if bpm == 120.0 and len(beats) == 5:
        record("TimelineService.beatgrid_metadata", "PASS", dt, details)
    else:
        record("TimelineService.beatgrid_metadata", "FAIL", dt, details)
except Exception as e:
    dt = time.perf_counter() - t0
    record("TimelineService.beatgrid_metadata", "CRASH", dt, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")

# 7h: clear
print("\n--- TEST 7h: TimelineService.clear ---")
t0 = time.perf_counter()
try:
    ts.clear()
    clips_after_clear = ts.get_all_clips()
    markers_after_clear = ts.get_markers()
    dt = time.perf_counter() - t0
    details = f"Clips nach clear={len(clips_after_clear)}, Markers={len(markers_after_clear)}"
    if len(clips_after_clear) == 0 and len(markers_after_clear) == 0:
        record("TimelineService.clear", "PASS", dt, details)
    else:
        record("TimelineService.clear", "FAIL", dt, details)
except Exception as e:
    dt = time.perf_counter() - t0
    record("TimelineService.clear", "CRASH", dt, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


# ====================================================================
#  TEST 8: apply_auto_edit_segments()
# ====================================================================
print("\n--- TEST 8: apply_auto_edit_segments() ---")
t0 = time.perf_counter()
try:
    from services.timeline_service import apply_auto_edit_segments
    segments = [
        {"video_id": CLIP_ID, "start": 0.0, "end": 2.0, "source_start": 0.0, "source_end": 2.0},
        {"video_id": CLIP_ID, "start": 2.0, "end": 4.0, "source_start": 3.0, "source_end": 5.0},
        {"video_id": CLIP_ID, "start": 4.0, "end": 5.0, "source_start": 7.0, "source_end": 8.0},
    ]
    count = apply_auto_edit_segments(segments, project_id=PROJECT_ID)
    dt = time.perf_counter() - t0
    # Verifiziere in DB
    with Session(engine) as session:
        entries = session.query(TimelineEntry).filter_by(
            project_id=PROJECT_ID, track="video"
        ).order_by(TimelineEntry.start_time).all()
        db_count = len(entries)
    details = f"Eingefuegt={count}, DB-Count={db_count}"
    if count == 3 and db_count == 3:
        record("apply_auto_edit_segments()", "PASS", dt, details)
    else:
        record("apply_auto_edit_segments()", "FAIL", dt, details)
except Exception as e:
    dt = time.perf_counter() - t0
    record("apply_auto_edit_segments()", "CRASH", dt, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


# ====================================================================
#  TEST 9: export_timeline() mit Multi-Segment Auto-Edit
# ====================================================================
print("\n--- TEST 9: export_timeline() mit 3 Auto-Edit Segmenten ---")
t0 = time.perf_counter()
try:
    result_path = export_timeline(
        project_id=PROJECT_ID,
        output_name="test_autoedit_export.mp4",
        resolution="1280x720",
        fps=30.0,
    )
    dt = time.perf_counter() - t0
    out_path = Path(result_path)
    if out_path.exists() and out_path.stat().st_size > 0:
        size = out_path.stat().st_size
        props = probe_output(out_path)
        record("export_timeline(multi-seg)", "PASS", dt, "3 Segmente exportiert", out_path, size, props)
    else:
        record("export_timeline(multi-seg)", "FAIL", dt, f"Datei fehlt: {result_path}")
except Exception as e:
    dt = time.perf_counter() - t0
    record("export_timeline(multi-seg)", "CRASH", dt, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


# ====================================================================
#  TEST 10: get_timeline_summary()
# ====================================================================
print("\n--- TEST 10: get_timeline_summary() ---")
t0 = time.perf_counter()
try:
    from services.export_service import get_timeline_summary
    summary = get_timeline_summary(project_id=PROJECT_ID)
    dt = time.perf_counter() - t0
    details = f"video_clips={summary.get('video_clips')}, audio_tracks={summary.get('audio_tracks')}, total_entries={summary.get('total_entries')}, duration={summary.get('estimated_duration')}"
    if summary.get("video_clips", 0) > 0:
        record("get_timeline_summary()", "PASS", dt, details)
    else:
        record("get_timeline_summary()", "FAIL", dt, details)
except Exception as e:
    dt = time.perf_counter() - t0
    record("get_timeline_summary()", "CRASH", dt, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


# ====================================================================
#  ZUSAMMENFASSUNG
# ====================================================================
print("\n\n" + "=" * 70)
print("  ERGEBNIS-ZUSAMMENFASSUNG")
print("=" * 70)

pass_count = sum(1 for r in RESULTS if r["status"] == "PASS")
fail_count = sum(1 for r in RESULTS if r["status"] == "FAIL")
crash_count = sum(1 for r in RESULTS if r["status"] == "CRASH")
total = len(RESULTS)

print(f"\n  GESAMT: {total} Tests | PASS: {pass_count} | FAIL: {fail_count} | CRASH: {crash_count}")
print(f"  Erfolgsquote: {pass_count}/{total} ({100*pass_count/total:.0f}%)" if total > 0 else "  Keine Tests")
print()

for r in RESULTS:
    icon = "PASS" if r["status"] == "PASS" else "FAIL" if r["status"] == "FAIL" else "CRASH"
    size_info = f" [{r.get('output_size_mb', '')} MB]" if 'output_size_mb' in r else ""
    props_info = ""
    if r.get("video_props"):
        vp = r["video_props"]
        props_info = f" ({vp.get('width')}x{vp.get('height')} {vp.get('codec')} @{vp.get('fps')}fps)"
    print(f"  [{icon}] {r['test']}  ({r['duration_sec']}s){size_info}{props_info}")

print()

# Cleanup: Temp-Verzeichnisse auflisten (nicht loeschen — User koennte inspizieren wollen)
print(f"  Temp-Projekt: {TEMP_PROJECT}")
print(f"  Temp-Convert: {temp_convert_dir}")
print(f"  (Aufraeumen: manuell loeschen wenn nicht mehr gebraucht)")

# Restore original APP_ROOT
db_session.APP_ROOT = original_app_root

print("\n" + "=" * 70)
print("  TESTS ABGESCHLOSSEN")
print("=" * 70)
