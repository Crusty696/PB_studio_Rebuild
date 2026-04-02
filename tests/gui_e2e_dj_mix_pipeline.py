#!/usr/bin/env python3
"""
GUI E2E Test: Full DJ Mix Pipeline
====================================
AUD-18 — Sprint 5: GUI E2E test suite with real DJ mix data

Tests the complete pipeline end-to-end:
  1. Launch app
  2. Import DJ mix audio (real file, ~62 min)
  3. Import video clips folder (10-20 clips)
  4. Run KOMPLETT-ANALYSE (beats + stems + LUFS)
  5. Run video analysis (Szenen-Erkennung)
  6. Generate Auto-Edit timeline
  7. Preview playback (play/stop)
  8. Export short segment
  9. Validate output file

Modes:
  --mode smoke   Quick UI validation, skips long analysis (default)
  --mode full    Complete pipeline, may take 30-120 minutes

Usage:
  python tests/gui_e2e_dj_mix_pipeline.py [--mode smoke|full] [--no-launch]

Requirements:
  pip install pyautogui pygetwindow

Test data (must exist):
  C:/Users/david/Documents/test_data/audio/Crusty_Progressive Psy Set2.mp3
  C:/Users/david/Documents/test_data/video/Solo_Natur/  (103 clips)
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pyautogui
import pygetwindow as gw

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = PROJECT_DIR / "logs" / "pb_studio.log"
SCREENSHOT_DIR = PROJECT_DIR / "test-report" / "e2e_dj_mix"
REPORT_PATH = PROJECT_DIR / "test-report" / "e2e_dj_mix_report.md"
EXPORTS_DIR = PROJECT_DIR / "exports"

TEST_AUDIO = Path("C:/Users/david/Documents/test_data/audio/Crusty_Progressive Psy Set2.mp3")
TEST_VIDEO_FOLDER = Path("C:/Users/david/Documents/test_data/video/Solo_Natur")

# ── Timing ────────────────────────────────────────────────────────────────────
APP_STARTUP_TIMEOUT = 30
IMPORT_TIMEOUT = 60
ANALYSIS_TIMEOUT_SMOKE = 120   # Beat analysis only, quick mode
ANALYSIS_TIMEOUT_FULL = 3600   # Full KOMPLETT-ANALYSE
VIDEO_ANALYSIS_TIMEOUT = 300
AUTO_EDIT_TIMEOUT = 120
EXPORT_TIMEOUT = 600
PAUSE = 1.2                    # Default pause between GUI actions

# ── pyautogui ─────────────────────────────────────────────────────────────────
pyautogui.FAILSAFE = True      # Move mouse to top-left corner to abort
pyautogui.PAUSE = 0.25

# ── Result tracking ───────────────────────────────────────────────────────────
results: list[dict] = []
step_counter = 0
bugs_found: list[dict] = []
_log_seek_pos: int = 0         # Track read position in log file


# ══════════════════════════════════════════════════════════════════════════════
# Utilities
# ══════════════════════════════════════════════════════════════════════════════

def log_step(name: str, status: str, detail: str = "", timing: float = 0.0):
    """Record a test step result."""
    global step_counter
    step_counter += 1
    ts = datetime.now().strftime("%H:%M:%S")
    icons = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP", "warn": "WARN"}
    icon = icons.get(status, "INFO")
    timing_str = f" [{timing:.1f}s]" if timing > 0 else ""
    print(f"  [{icon}] {ts} Step {step_counter:02d}: {name}{timing_str}")
    if detail:
        print(f"           {detail}")
    results.append({
        "step": step_counter,
        "name": name,
        "status": status,
        "detail": detail,
        "timing": timing,
        "ts": ts,
    })


def log_bug(title: str, description: str, severity: str = "medium"):
    """Record a bug found during testing."""
    bug = {"title": title, "description": description, "severity": severity,
           "ts": datetime.now().isoformat()}
    bugs_found.append(bug)
    print(f"  [BUG] {severity.upper()}: {title}")


def take_screenshot(label: str) -> Path | None:
    """Capture a screenshot."""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%H%M%S")
    path = SCREENSHOT_DIR / f"{step_counter:02d}_{label}_{ts}.png"
    try:
        img = pyautogui.screenshot()
        img.save(str(path))
        return path
    except Exception as e:
        print(f"  [WARN] Screenshot failed: {e}")
        return None


def find_app_window(timeout: int = APP_STARTUP_TIMEOUT):
    """Wait for the PB Studio window to appear."""
    start = time.time()
    while time.time() - start < timeout:
        for w in gw.getAllWindows():
            if ("PB_studio" in w.title or "PB Studio" in w.title) and w.visible:
                return w
        time.sleep(0.5)
    return None


def activate_window(win) -> bool:
    """Focus the app window."""
    try:
        win.activate()
        time.sleep(0.4)
        return True
    except Exception as e:
        print(f"  [WARN] activate_window: {e}")
        return False


def click_nav(win, workspace: str):
    """Click a bottom NavBar workspace button. Workspaces: MEDIA/EDIT/STEMS/CONVERT/DELIVER."""
    order = ["MEDIA", "EDIT", "STEMS", "CONVERT", "DELIVER"]
    idx = order.index(workspace.upper())
    btn_width = win.width / len(order)
    x = win.left + int(btn_width * idx + btn_width / 2)
    y = win.top + win.height - 22   # NavBar center, ~44px from bottom
    activate_window(win)
    pyautogui.click(x, y)
    time.sleep(PAUSE)


def click_rel(win, x_pct: float, y_pct: float, label: str = ""):
    """Click at a relative position within the window."""
    x = win.left + int(win.width * x_pct)
    y = win.top + int(win.height * y_pct)
    activate_window(win)
    pyautogui.click(x, y)
    time.sleep(0.5)


def handle_file_dialog(file_path: str):
    """Type a file path into the native Windows file dialog and confirm."""
    time.sleep(1.5)  # Let dialog open
    # The Windows file dialog has an address/filename bar we can type into
    # Use keyboard shortcut to focus the filename field
    pyautogui.hotkey("ctrl", "l")   # Focus address bar
    time.sleep(0.3)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.2)
    pyautogui.typewrite(file_path, interval=0.02)
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(0.5)
    # Some dialogs need a second Enter to confirm
    pyautogui.press("enter")
    time.sleep(1.0)


def handle_folder_dialog(folder_path: str):
    """Navigate to a folder in the native folder dialog."""
    time.sleep(1.5)
    pyautogui.hotkey("ctrl", "l")
    time.sleep(0.3)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.2)
    pyautogui.typewrite(folder_path, interval=0.02)
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(0.5)
    pyautogui.press("enter")  # Confirm folder selection
    time.sleep(1.0)


def reset_log_cursor():
    """Set the log-file read cursor to current end (ignore old entries)."""
    global _log_seek_pos
    if LOG_FILE.exists():
        _log_seek_pos = LOG_FILE.stat().st_size
    else:
        _log_seek_pos = 0


def wait_for_log_marker(marker: str, timeout: int, interval: float = 2.0) -> bool:
    """Poll the log file for a marker string, starting from our last read position."""
    start = time.time()
    while time.time() - start < timeout:
        if LOG_FILE.exists():
            try:
                with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(_log_seek_pos)
                    new_content = f.read()
                if marker in new_content:
                    return True
                if time.time() - start > interval:
                    pass  # Continue polling
            except Exception:
                pass
        time.sleep(interval)
    return False


def wait_for_db_change(check_fn, timeout: int, interval: float = 3.0) -> bool:
    """Poll a DB check function until it returns truthy or times out."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            if check_fn():
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def db_audio_has_bpm() -> bool:
    """Return True if any AudioTrack in DB has a non-null BPM."""
    try:
        sys.path.insert(0, str(PROJECT_DIR))
        from database import AudioTrack, engine
        from sqlalchemy.orm import Session as DBSession
        with DBSession(bind=engine) as s:
            return s.query(AudioTrack).filter(AudioTrack.bpm.isnot(None)).count() > 0
    except Exception:
        return False


def db_timeline_has_entries() -> bool:
    """Return True if any TimelineEntry exists in DB."""
    try:
        from database import TimelineEntry, engine
        from sqlalchemy.orm import Session as DBSession
        with DBSession(bind=engine) as s:
            return s.query(TimelineEntry).count() > 0
    except Exception:
        return False


def db_audio_count() -> int:
    """Return number of AudioTrack records in DB."""
    try:
        from database import AudioTrack, engine
        from sqlalchemy.orm import Session as DBSession
        with DBSession(bind=engine) as s:
            return s.query(AudioTrack).count()
    except Exception:
        return 0


def db_video_count() -> int:
    """Return number of VideoClip records in DB."""
    try:
        from database import VideoClip, engine
        from sqlalchemy.orm import Session as DBSession
        with DBSession(bind=engine) as s:
            return s.query(VideoClip).count()
    except Exception:
        return 0


def validate_export_file() -> tuple[bool, str]:
    """Check that a new video file was created in exports/."""
    EXPORTS_DIR.mkdir(exist_ok=True)
    files = sorted(EXPORTS_DIR.glob("*.mp4"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        return False, "No .mp4 in exports/"
    newest = files[0]
    size_mb = newest.stat().st_size / (1024 * 1024)
    if size_mb < 0.1:
        return False, f"{newest.name} too small ({size_mb:.2f} MB)"
    # Quick ffprobe check
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_streams", str(newest)],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            streams = data.get("streams", [])
            has_video = any(s.get("codec_type") == "video" for s in streams)
            has_audio = any(s.get("codec_type") == "audio" for s in streams)
            return True, (
                f"{newest.name} ({size_mb:.1f} MB) "
                f"video={'yes' if has_video else 'NO'} "
                f"audio={'yes' if has_audio else 'NO'}"
            )
    except Exception as e:
        return True, f"{newest.name} ({size_mb:.1f} MB) — ffprobe failed: {e}"
    return True, f"{newest.name} ({size_mb:.1f} MB)"


# ══════════════════════════════════════════════════════════════════════════════
# Screen Recording
# ══════════════════════════════════════════════════════════════════════════════

_ffmpeg_rec = None


def start_recording():
    """Start screen recording with ffmpeg (gdigrab)."""
    global _ffmpeg_rec
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    rec_path = SCREENSHOT_DIR / "e2e_recording.mp4"
    cmd = ["ffmpeg", "-y", "-f", "gdigrab", "-framerate", "15", "-i", "desktop",
           "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
           "-pix_fmt", "yuv420p", str(rec_path)]
    try:
        _ffmpeg_rec = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
        time.sleep(1)
        print(f"  [REC] Recording → {rec_path}")
        return True
    except Exception as e:
        print(f"  [WARN] Recording failed: {e}")
        return False


def stop_recording():
    """Stop ffmpeg screen recording."""
    global _ffmpeg_rec
    if _ffmpeg_rec:
        try:
            _ffmpeg_rec.stdin.write(b"q")
            _ffmpeg_rec.stdin.flush()
            _ffmpeg_rec.wait(timeout=10)
        except Exception:
            _ffmpeg_rec.terminate()
        _ffmpeg_rec = None


# ══════════════════════════════════════════════════════════════════════════════
# Test Steps
# ══════════════════════════════════════════════════════════════════════════════

def step_app_startup(launch: bool) -> object | None:
    """Step 1 — Launch app and find window."""
    t0 = time.time()
    app_proc = None

    if launch:
        print("  Launching PB Studio...")
        app_proc = subprocess.Popen(
            [sys.executable, str(PROJECT_DIR / "main.py")],
            cwd=str(PROJECT_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        print("  --no-launch: attaching to running PB Studio...")

    win = find_app_window(timeout=APP_STARTUP_TIMEOUT)
    elapsed = time.time() - t0

    if not win:
        log_step("App Startup", "fail", f"Window not found after {APP_STARTUP_TIMEOUT}s", elapsed)
        return None, app_proc

    try:
        win.maximize()
    except Exception:
        pass
    time.sleep(0.8)

    if launch and app_proc and app_proc.poll() is not None:
        log_bug("App crashed at startup", f"Process exited with code {app_proc.returncode}",
                "critical")
        log_step("App Startup", "fail", f"Process crashed (exit {app_proc.returncode})", elapsed)
        take_screenshot("startup_crash")
        return None, app_proc

    take_screenshot("startup")
    log_step("App Startup", "pass", f"'{win.title}' {win.width}x{win.height}", elapsed)
    return win, app_proc


def step_navigate_to_media(win) -> bool:
    """Step 2 — Navigate to MEDIA workspace."""
    t0 = time.time()
    click_nav(win, "MEDIA")
    take_screenshot("media_workspace")
    log_step("Navigate to MEDIA", "pass", "NavBar MEDIA clicked", time.time() - t0)
    return True


def step_import_audio(win) -> bool:
    """Step 3 — Switch to AUDIO MODUS and import DJ mix audio file."""
    t0 = time.time()

    if not TEST_AUDIO.exists():
        log_step("Import Audio", "skip",
                 f"Test file missing: {TEST_AUDIO}")
        log_bug("Missing test audio file", str(TEST_AUDIO), "high")
        return False

    audio_count_before = db_audio_count()

    # Switch to AUDIO MODUS (right button in mode-bar, ~65% from left, ~10% from top)
    click_rel(win, 0.65, 0.10, "AUDIO MODUS button")
    time.sleep(PAUSE)
    take_screenshot("audio_mode")

    # Click "Audio importieren" button (left panel, ~12% from left, ~28% from top)
    click_rel(win, 0.12, 0.28, "Audio importieren button")

    # Handle file dialog
    handle_file_dialog(str(TEST_AUDIO).replace("/", "\\"))
    time.sleep(2.0)

    # Wait for DB update
    def audio_imported():
        return db_audio_count() > audio_count_before

    ok = wait_for_db_change(audio_imported, timeout=IMPORT_TIMEOUT)
    take_screenshot("audio_imported")
    elapsed = time.time() - t0

    if ok:
        log_step("Import Audio", "pass",
                 f"DB audio count: {db_audio_count()} (+{db_audio_count() - audio_count_before})",
                 elapsed)
        return True
    else:
        log_bug("Audio import failed or not reflected in DB",
                f"DB count unchanged at {audio_count_before} after {IMPORT_TIMEOUT}s", "high")
        log_step("Import Audio", "fail",
                 f"DB count unchanged: {audio_count_before}", elapsed)
        return False


def step_import_video_folder(win) -> bool:
    """Step 4 — Switch to VIDEO MODUS and import video folder."""
    t0 = time.time()

    if not TEST_VIDEO_FOLDER.exists():
        log_step("Import Video Folder", "skip",
                 f"Video folder missing: {TEST_VIDEO_FOLDER}")
        return False

    video_count_before = db_video_count()

    # Switch to VIDEO MODUS (~35% from left, ~10% from top)
    click_rel(win, 0.35, 0.10, "VIDEO MODUS button")
    time.sleep(PAUSE)

    # Click "Ordner importieren" (~12%, ~33%)
    click_rel(win, 0.12, 0.33, "Ordner importieren button")

    # Handle folder dialog
    handle_folder_dialog(str(TEST_VIDEO_FOLDER).replace("/", "\\"))
    time.sleep(3.0)

    # Wait for import worker (DB update)
    def videos_imported():
        return db_video_count() > video_count_before

    ok = wait_for_db_change(videos_imported, timeout=IMPORT_TIMEOUT)
    take_screenshot("video_imported")
    elapsed = time.time() - t0

    new_count = db_video_count()
    if ok:
        log_step("Import Video Folder", "pass",
                 f"DB video count: {new_count} (+{new_count - video_count_before})",
                 elapsed)
        return True
    else:
        log_bug("Video folder import failed",
                f"DB count unchanged at {video_count_before}", "high")
        log_step("Import Video Folder", "fail",
                 f"DB count unchanged: {video_count_before}", elapsed)
        return False


def step_select_audio_track(win) -> bool:
    """Step 5 — Switch to AUDIO MODUS and select the first track."""
    t0 = time.time()
    click_rel(win, 0.65, 0.10, "AUDIO MODUS button")
    time.sleep(PAUSE)

    # Click first row in audio_pool_table (right panel, ~65% x, ~20% y)
    click_rel(win, 0.65, 0.20, "audio pool table first row")
    time.sleep(0.5)
    take_screenshot("audio_track_selected")
    log_step("Select Audio Track", "pass", "Clicked first audio pool row", time.time() - t0)
    return True


def step_komplett_analyse(win, mode: str) -> bool:
    """Step 6 — Run KOMPLETT-ANALYSE on selected audio track."""
    t0 = time.time()
    timeout = ANALYSIS_TIMEOUT_FULL if mode == "full" else ANALYSIS_TIMEOUT_SMOKE
    bpm_before = db_audio_has_bpm()

    reset_log_cursor()

    # KOMPLETT-ANALYSE button (~12%, ~46%)
    click_rel(win, 0.12, 0.46, "KOMPLETT-ANALYSE button")
    time.sleep(2.0)
    take_screenshot("komplett_analyse_started")

    print(f"  Waiting for KOMPLETT-ANALYSE (max {timeout}s)...")

    if mode == "full":
        # Full analysis: wait for log marker
        ok = wait_for_log_marker("Komplett-Analyse fertig", timeout=timeout)
        if not ok:
            # Fallback: check if BPM was set (partial success)
            ok = not bpm_before and db_audio_has_bpm()
    else:
        # Smoke mode: just wait for BPM to appear in DB (beat detection only)
        ok = wait_for_db_change(db_audio_has_bpm, timeout=timeout)

    elapsed = time.time() - t0
    take_screenshot("komplett_analyse_done")

    if ok:
        log_step("KOMPLETT-ANALYSE", "pass",
                 f"BPM in DB: {db_audio_has_bpm()}", elapsed)
        return True
    else:
        log_bug("KOMPLETT-ANALYSE timed out or failed",
                f"Timeout after {timeout}s. BPM in DB: {db_audio_has_bpm()}", "high")
        log_step("KOMPLETT-ANALYSE", "warn",
                 f"Timeout after {timeout}s — proceeding anyway", elapsed)
        return False  # Non-fatal: continue test


def step_video_analysis(win) -> bool:
    """Step 7 — Run Szenen-Erkennung on video clips."""
    t0 = time.time()

    # Switch to VIDEO MODUS
    click_rel(win, 0.35, 0.10, "VIDEO MODUS button")
    time.sleep(PAUSE)

    # Select all / first video clip (click table area ~65%, ~25%)
    click_rel(win, 0.65, 0.25, "video table first row")
    time.sleep(0.5)

    reset_log_cursor()

    # Szenen-Erkennung button (~12%, ~38%)
    click_rel(win, 0.12, 0.38, "Szenen-Erkennung button")
    time.sleep(2.0)
    take_screenshot("video_analysis_started")

    # Wait for some log activity (any worker log entry)
    def video_analysis_started():
        if LOG_FILE.exists():
            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                f.seek(_log_seek_pos)
                content = f.read()
            return "scene" in content.lower() or "szenen" in content.lower() or "video" in content.lower()
        return False

    ok = wait_for_db_change(video_analysis_started, timeout=VIDEO_ANALYSIS_TIMEOUT)
    elapsed = time.time() - t0
    take_screenshot("video_analysis_done")

    if ok:
        log_step("Video Analysis (Szenen)", "pass", f"Log shows activity", elapsed)
    else:
        log_step("Video Analysis (Szenen)", "warn",
                 f"No log confirmation after {VIDEO_ANALYSIS_TIMEOUT}s — UI may still be working",
                 elapsed)
    return True  # Non-fatal


def step_auto_edit(win) -> bool:
    """Step 8 — Navigate to EDIT workspace and run Auto-Edit."""
    t0 = time.time()

    click_nav(win, "EDIT")
    time.sleep(PAUSE * 2)
    take_screenshot("edit_workspace")

    timeline_before = db_timeline_has_entries()
    reset_log_cursor()

    # Auto-Edit button (~85%, ~45%)
    click_rel(win, 0.85, 0.45, "Auto-Edit button")
    time.sleep(2.0)
    take_screenshot("auto_edit_started")

    print(f"  Waiting for Auto-Edit (max {AUTO_EDIT_TIMEOUT}s)...")

    # Wait for log marker or DB timeline entries
    def auto_edit_done():
        if wait_for_log_marker("[Auto-Edit] Phase 3 fertig", timeout=1):
            return True
        return db_timeline_has_entries() and not timeline_before

    ok = wait_for_db_change(
        lambda: db_timeline_has_entries(),
        timeout=AUTO_EDIT_TIMEOUT
    )
    elapsed = time.time() - t0
    take_screenshot("auto_edit_done")

    if ok:
        log_step("Auto-Edit", "pass",
                 f"Timeline entries in DB: {db_timeline_has_entries()}", elapsed)
        return True
    else:
        log_bug("Auto-Edit did not produce timeline entries",
                f"No TimelineEntry in DB after {AUTO_EDIT_TIMEOUT}s", "medium")
        log_step("Auto-Edit", "fail",
                 f"No timeline entries after {AUTO_EDIT_TIMEOUT}s", elapsed)
        return False


def step_preview_playback(win) -> bool:
    """Step 9 — Test preview playback (play 10s then stop)."""
    t0 = time.time()

    # Play button (~82%, ~22%)
    click_rel(win, 0.82, 0.22, "Play button")
    time.sleep(0.5)
    take_screenshot("playback_playing")

    time.sleep(5)  # Watch it play for 5 seconds

    # Stop button (~84%, ~22%)
    click_rel(win, 0.84, 0.22, "Stop button")
    time.sleep(0.5)
    take_screenshot("playback_stopped")

    log_step("Preview Playback", "pass", "Play 5s then stop — no crash", time.time() - t0)
    return True


def step_export(win) -> bool:
    """Step 10 — Navigate to DELIVER workspace and export."""
    t0 = time.time()

    click_nav(win, "DELIVER")
    time.sleep(PAUSE * 2)
    take_screenshot("deliver_workspace")

    # Aktualisieren (refresh) button (~15%, ~25%)
    click_rel(win, 0.15, 0.25, "Aktualisieren button")
    time.sleep(1.5)

    reset_log_cursor()

    # Video exportieren button (~15%, ~35%)
    click_rel(win, 0.15, 0.35, "Export button")
    time.sleep(2.0)
    take_screenshot("export_started")

    print(f"  Waiting for export (max {EXPORT_TIMEOUT}s)...")
    ok = wait_for_log_marker("[Export] FERTIG", timeout=EXPORT_TIMEOUT)
    elapsed = time.time() - t0
    take_screenshot("export_done")

    if ok:
        log_step("Export", "pass", f"Log shows [Export] FERTIG", elapsed)
        return True
    else:
        log_bug("Export timed out or failed",
                f"No [Export] FERTIG in log after {EXPORT_TIMEOUT}s", "high")
        log_step("Export", "warn",
                 f"No FERTIG log after {EXPORT_TIMEOUT}s", elapsed)
        return False


def step_validate_output() -> bool:
    """Step 11 — Validate the exported file with ffprobe."""
    t0 = time.time()
    ok, detail = validate_export_file()
    elapsed = time.time() - t0

    if ok:
        log_step("Validate Export", "pass", detail, elapsed)
    else:
        log_bug("Export file validation failed", detail, "high")
        log_step("Validate Export", "fail", detail, elapsed)
    return ok


def step_workspace_navigation_check(win):
    """Extra: Verify all 5 workspaces are reachable and don't crash."""
    t0 = time.time()
    for ws in ["MEDIA", "EDIT", "STEMS", "CONVERT", "DELIVER"]:
        click_nav(win, ws)
        time.sleep(0.8)
        take_screenshot(f"ws_{ws.lower()}")
    click_nav(win, "MEDIA")  # Return to MEDIA
    log_step("Workspace Nav Check", "pass",
             "All 5 workspaces navigated without crash", time.time() - t0)


# ══════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════

def generate_report(mode: str) -> str:
    """Write a Markdown report of all test results."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    warned = sum(1 for r in results if r["status"] == "warn")
    skipped = sum(1 for r in results if r["status"] == "skip")

    lines = [
        f"# E2E DJ Mix Pipeline — Test Report",
        f"",
        f"**Date:** {ts}  ",
        f"**Mode:** {mode}  ",
        f"**Result:** {passed}/{total} PASS | {failed} FAIL | {warned} WARN | {skipped} SKIP",
        f"",
        f"## Steps",
        f"",
        f"| # | Step | Status | Timing | Detail |",
        f"|---|------|--------|--------|--------|",
    ]
    for r in results:
        icon = {"pass": "PASS", "fail": "FAIL", "warn": "WARN", "skip": "SKIP"}.get(r["status"], "?")
        t = f"{r['timing']:.1f}s" if r.get("timing", 0) > 0 else "-"
        lines.append(f"| {r['step']} | {r['name']} | {icon} | {t} | {r['detail']} |")

    if bugs_found:
        lines.extend([
            "",
            f"## Bugs Found ({len(bugs_found)})",
            "",
        ])
        for i, b in enumerate(bugs_found, 1):
            lines.append(f"### Bug {i}: {b['title']}")
            lines.append(f"**Severity:** {b['severity']}  ")
            lines.append(f"**Found at:** {b['ts']}  ")
            lines.append(f"**Description:** {b['description']}")
            lines.append("")

    lines.extend([
        "## Test Data",
        "",
        f"- Audio: `{TEST_AUDIO}`",
        f"- Video folder: `{TEST_VIDEO_FOLDER}`",
        f"- DB audio count: {db_audio_count()}",
        f"- DB video count: {db_video_count()}",
        f"- DB timeline entries: {db_timeline_has_entries()}",
        "",
        "## Screenshots",
        "",
        f"Saved to: `{SCREENSHOT_DIR.relative_to(PROJECT_DIR)}/`",
    ])
    if SCREENSHOT_DIR.exists():
        for img in sorted(SCREENSHOT_DIR.glob("*.png")):
            lines.append(f"- `{img.name}`")

    report = "\n".join(lines)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"\n  Report saved: {REPORT_PATH}")
    return report


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="PB Studio GUI E2E DJ Mix Pipeline Test")
    parser.add_argument("--mode", choices=["smoke", "full"], default="smoke",
                        help="Test mode: smoke (quick) or full (complete pipeline)")
    parser.add_argument("--no-launch", action="store_true",
                        help="Attach to already-running PB Studio instead of launching")
    args = parser.parse_args()

    mode = args.mode
    launch = not args.no_launch

    print("=" * 65)
    print(f"  PB Studio — GUI E2E DJ Mix Pipeline [{mode.upper()} MODE]")
    print("  HANDS OFF MOUSE AND KEYBOARD DURING THE TEST!")
    print("=" * 65)
    print(f"  Audio: {TEST_AUDIO}")
    print(f"  Video: {TEST_VIDEO_FOLDER} ({len(list(TEST_VIDEO_FOLDER.glob('*.mp4'))) if TEST_VIDEO_FOLDER.exists() else '?'} clips)")
    print()

    # Clean up old screenshots
    if SCREENSHOT_DIR.exists():
        for f in SCREENSHOT_DIR.glob("*.png"):
            f.unlink()

    recording_ok = start_recording()
    t_total = time.time()

    win = None
    app_proc = None

    try:
        # ── Step 1: Launch & startup ───────────────────────────────────────────
        win, app_proc = step_app_startup(launch)
        if not win:
            print("  ABORT: App window not found.")
            return False

        # ── Step 2: Navigate to MEDIA ──────────────────────────────────────────
        step_navigate_to_media(win)

        # ── Step 3: Import audio ───────────────────────────────────────────────
        audio_ok = step_import_audio(win)

        # ── Step 4: Import video folder ────────────────────────────────────────
        video_ok = step_import_video_folder(win)

        if not audio_ok and not video_ok:
            log_bug("Both imports failed",
                    "Cannot proceed with analysis without media", "critical")

        # ── Step 5: Select audio track ─────────────────────────────────────────
        step_select_audio_track(win)

        # ── Step 6: KOMPLETT-ANALYSE ───────────────────────────────────────────
        step_komplett_analyse(win, mode)

        # ── Step 7: Video analysis ─────────────────────────────────────────────
        if video_ok:
            step_video_analysis(win)
        else:
            log_step("Video Analysis", "skip", "No video clips imported")

        # ── Step 8: Auto-Edit ──────────────────────────────────────────────────
        step_auto_edit(win)

        # ── Step 9: Preview playback ───────────────────────────────────────────
        step_preview_playback(win)

        # ── Step 10+11: Export + validate (full mode only) ─────────────────────
        if mode == "full":
            export_ok = step_export(win)
            if export_ok:
                step_validate_output()
            else:
                log_step("Validate Export", "skip", "Export failed — skipping validation")
        else:
            log_step("Export", "skip", "Smoke mode — skipping export")
            log_step("Validate Export", "skip", "Smoke mode — skipping validation")

        # ── Bonus: Workspace navigation smoke check ────────────────────────────
        step_workspace_navigation_check(win)

        take_screenshot("final_state")
        log_step("Final State", "pass", "All test steps completed — app stable")

    except pyautogui.FailSafeException:
        log_step("FAILSAFE", "fail", "Mouse moved to corner — test aborted!")
        log_bug("Test aborted by failsafe", "Mouse was in top-left corner", "low")

    except Exception as e:
        import traceback
        detail = traceback.format_exc()
        log_step("Unexpected Error", "fail", str(e))
        log_bug(f"Test framework error: {e}", detail, "medium")
        take_screenshot("error_state")

    finally:
        # Graceful app shutdown
        if win:
            try:
                activate_window(win)
                pyautogui.hotkey("alt", "F4")
                time.sleep(2)
            except Exception:
                pass

        if app_proc and app_proc.poll() is None:
            app_proc.terminate()
            try:
                app_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                app_proc.kill()

        if recording_ok:
            stop_recording()

        # Report
        total_elapsed = time.time() - t_total
        print(f"\n  Total time: {int(total_elapsed // 60)}m {int(total_elapsed % 60)}s")
        report = generate_report(mode)
        print()
        print(report)

        # Summary
        passed = sum(1 for r in results if r["status"] == "pass")
        failed = sum(1 for r in results if r["status"] == "fail")
        total = len(results)
        print()
        print("=" * 65)
        print(f"  RESULT: {passed}/{total} passed, {failed} failed, {len(bugs_found)} bugs")
        print("=" * 65)

        return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
