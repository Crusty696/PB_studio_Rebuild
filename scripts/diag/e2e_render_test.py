"""
E2E Render Test — Launches PB Studio GUI and triggers a full 1+ hour export.

This script:
1. Launches PB Studio with its full GUI
2. Navigates to the DELIVER workspace
3. Sets export parameters (854x480, 30fps, H.264 fast)
4. Triggers the "Video exportieren" button
5. Monitors progress until completion
6. Verifies the output file

The timeline must be pre-populated in the database before running this script.
"""

# === IMPORTANT: Reuse main.py's early init (CUDA, FFmpeg, DLL paths) ===
# This import triggers all the module-level setup in main.py
from dotenv import load_dotenv
load_dotenv()

import os
import sys
import time
import logging
from pathlib import Path

# Copy main.py's early PATH setup
_APP_ROOT = Path(__file__).resolve().parents[2]  # scripts/diag/ -> Repo-Root (CRF-020-Move-Fix)
_BIN_DIR = str(_APP_ROOT / "bin")
if _BIN_DIR not in os.environ["PATH"]:
    os.environ["PATH"] = _BIN_DIR + os.pathsep + os.environ["PATH"]

# CUDA DLL injection (same as main.py)
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
        if any((d / n).exists() for n in ("nvcuda64.dll", "nvcuda.dll", "OpenCL64.dll")):
            return str(d)
    return str(candidates[0]) if candidates else None

_NV_DRIVER = _find_nv_driver_dir()
# B-215: torch-DLLs aus AKTUELLEM Interpreter (sys.prefix), nicht hardcoded venv.
# Conda-env oder venv beide unterstuetzt. Fallback fuer Edge-Cases.
import sys as _sys
_INTERP_TORCH = Path(_sys.prefix) / "Lib" / "site-packages" / "torch" / "lib"
_VENV310_TORCH = _APP_ROOT / ".venv310" / "Lib" / "site-packages" / "torch" / "lib"
_VENV_TORCH = _APP_ROOT / ".venv" / "Lib" / "site-packages" / "torch" / "lib"
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
    if _p not in os.environ["PATH"]:
        os.environ["PATH"] = _p + os.pathsep + os.environ["PATH"]
    if hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(_p)
        except Exception:
            pass

# CUDA init
try:
    import torch
    if torch.cuda.is_available():
        torch.cuda.get_device_name(0)
except Exception:
    pass

# === PySide6 Imports ===
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, Qt

# === Setup Logging ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("e2e_render_test")

# === Patch startup dialog to auto-accept ===
try:
    import ui.dialogs.startup_check_dialog as _scd
    _orig = _scd.maybe_show_startup_dialog
    def _auto_accept(status, parent):
        logger.info("[E2E] Auto-accepting startup dialog (status: %s)",
                     getattr(status, 'status_bar_text', lambda: 'ok')())
        return True
    _scd.maybe_show_startup_dialog = _auto_accept
except Exception as e:
    logger.warning("[E2E] Could not patch startup dialog: %s", e)


# === Export Automation State ===
class E2EState:
    export_started = False
    export_finished = False
    export_error = None
    output_path = None
    start_time = None
    window = None


def run_export_automation():
    """Called after app startup to trigger the export via GUI widgets."""
    try:
        _run_export_automation_inner()
    except Exception as e:
        logger.error("[E2E] CRASH in export automation: %s", e, exc_info=True)
        write_result("FAILED", f"Automation crash: {e}")
        QTimer.singleShot(3000, lambda: QApplication.instance().quit())


def _run_export_automation_inner():
    """Inner implementation with full error propagation."""
    state = E2EState
    window = state.window

    if window is None:
        logger.error("[E2E] Window not initialized!")
        return

    logger.info("[E2E] ========== STARTING E2E RENDER TEST ==========")

    # Step 1: Navigate to EXPORT workspace (Phase 10: 4-Tab layout, EXPORT at index 3)
    logger.info("[E2E] Step 1: Navigating to EXPORT workspace (index 3)...")
    window.workspace_stack.setCurrentIndex(3)  # EXPORT (4 Tabs gesamt)
    window.export._refresh_production_info()
    QApplication.processEvents()

    # Step 2: Verify timeline info
    logger.info("[E2E] Step 2: Verifying timeline...")
    info_text = window.production_info.text()
    logger.info("[E2E] Timeline info: %s", info_text)

    # Step 3: Set export parameters
    logger.info("[E2E] Step 3: Setting export parameters...")

    # Filename
    window.export_name_input.clear()
    window.export_name_input.setText("final_e2e_all_clips.mp4")
    logger.info("[E2E]   Filename: final_e2e_all_clips.mp4")

    # Resolution: 854x480 (native clip resolution)
    res_idx = window.resolution_combo.findText("854x480")
    if res_idx >= 0:
        window.resolution_combo.setCurrentIndex(res_idx)
        logger.info("[E2E]   Resolution: 854x480")
    else:
        logger.warning("[E2E]   854x480 not found, using default: %s",
                       window.resolution_combo.currentText())

    # FPS: 30
    fps_idx = window.fps_combo.findText("30")
    if fps_idx >= 0:
        window.fps_combo.setCurrentIndex(fps_idx)
        logger.info("[E2E]   FPS: 30")

    # Preset: Standard (H.264 fast)
    preset_idx = window.preset_combo.findText("Standard (H.264 fast)")
    if preset_idx >= 0:
        window.preset_combo.setCurrentIndex(preset_idx)
        logger.info("[E2E]   Preset: Standard (H.264 fast)")

    QApplication.processEvents()

    # Step 4: Hook into export signals to track completion
    original_finished = window.export._on_export_finished
    original_error = window.export._on_export_error

    def on_finished_hook(output_path, task_id=""):
        try:
            state.export_finished = True
            state.output_path = output_path
            elapsed = time.time() - state.start_time if state.start_time else 0
            logger.info("[E2E] ========== EXPORT FINISHED ==========")
            logger.info("[E2E] Output: %s", output_path)
            logger.info("[E2E] Elapsed: %.1f seconds (%.1f minutes)", elapsed, elapsed / 60)
            original_finished(output_path, task_id)
            # Schedule verification
            QTimer.singleShot(1000, verify_output)
        except Exception as e:
            logger.error("[E2E] Error in finished hook: %s", e, exc_info=True)

    def on_error_hook(error_msg, task_id=""):
        try:
            state.export_finished = True
            state.export_error = error_msg
            elapsed = time.time() - state.start_time if state.start_time else 0
            logger.error("[E2E] ========== EXPORT FAILED ==========")
            logger.error("[E2E] Error: %s", error_msg)
            logger.error("[E2E] Elapsed: %.1f seconds", elapsed)
            original_error(error_msg, task_id)
            write_result("FAILED", f"Export error: {error_msg}")
            QTimer.singleShot(2000, lambda: QApplication.instance().quit())
        except Exception as e:
            logger.error("[E2E] Error in error hook: %s", e, exc_info=True)

    window.export._on_export_finished = on_finished_hook
    window.export._on_export_error = on_error_hook

    # Step 5: Click export button!
    logger.info("[E2E] Step 5: Clicking 'Video exportieren'...")
    state.start_time = time.time()
    state.export_started = True

    # This triggers the export via the GUI controller (same as clicking the button)
    window.btn_export.click()

    logger.info("[E2E] Export triggered. Monitoring progress...")

    # Start progress monitor
    monitor_timer = QTimer()
    monitor_timer.setInterval(30000)  # Log every 30 seconds

    def log_progress():
        try:
            if state.export_finished:
                monitor_timer.stop()
                return
            elapsed = time.time() - state.start_time if state.start_time else 0
            pct = window.export_progress.value() if window.export_progress.isVisible() else -1
            logger.info("[E2E] Progress: %d%% | Elapsed: %.0fs (%.1f min)",
                        pct, elapsed, elapsed / 60)
        except Exception as e:
            logger.error("[E2E] Progress monitor error: %s", e)

    monitor_timer.timeout.connect(log_progress)
    monitor_timer.start()
    # Keep reference to prevent GC
    window._e2e_monitor_timer = monitor_timer


def verify_output():
    """Verify the rendered output file meets requirements."""
    state = E2EState
    logger.info("[E2E] ========== VERIFICATION ==========")

    if state.export_error:
        logger.error("[E2E] FAILED: Export had error: %s", state.export_error)
        write_result("FAILED", f"Export error: {state.export_error}")
        QTimer.singleShot(2000, lambda: QApplication.instance().quit())
        return

    output_path = state.output_path
    if not output_path or not Path(output_path).exists():
        logger.error("[E2E] FAILED: Output file not found: %s", output_path)
        write_result("FAILED", f"Output file not found: {output_path}")
        QTimer.singleShot(2000, lambda: QApplication.instance().quit())
        return

    file_size = Path(output_path).stat().st_size
    file_size_mb = file_size / (1024 * 1024)
    logger.info("[E2E] Output file: %s", output_path)
    logger.info("[E2E] File size: %.1f MB", file_size_mb)

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
        duration_min = duration / 60
        logger.info("[E2E] Duration: %.1f seconds (%.1f minutes)", duration, duration_min)

        if duration >= 3600:
            logger.info("[E2E] PASS: Duration >= 1 hour (%.1f min)", duration_min)
        elif duration >= 3500:
            logger.info("[E2E] PASS (marginal): Duration ~1 hour (%.1f min)", duration_min)
        else:
            logger.warning("[E2E] WARNING: Duration < 1 hour (%.1f min)", duration_min)
    except Exception as e:
        logger.warning("[E2E] Could not check duration: %s", e)
        duration_min = -1

    elapsed = time.time() - state.start_time if state.start_time else 0

    result_msg = (
        f"Output: {output_path}\n"
        f"Size: {file_size_mb:.1f} MB\n"
        f"Duration: {duration_min:.1f} min\n"
        f"Render time: {elapsed:.0f}s ({elapsed/60:.1f} min)\n"
    )
    write_result("PASSED" if duration_min >= 58 else "WARNING", result_msg)

    logger.info("[E2E] ========== TEST COMPLETE ==========")
    logger.info("[E2E] Closing app in 5 seconds...")
    QTimer.singleShot(5000, lambda: QApplication.instance().quit())


def write_result(status, details):
    """Write test result to a file for external monitoring."""
    result_file = _APP_ROOT / "exports" / "e2e_render_result.txt"
    with open(result_file, "w", encoding="utf-8") as f:
        f.write(f"STATUS: {status}\n")
        f.write(f"TIMESTAMP: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"---\n{details}\n")
    logger.info("[E2E] Result written to: %s", result_file)


# === Main Entry Point ===
if __name__ == "__main__":
    # Import main.py's setup_logging
    from main import setup_logging as _setup_log, APP_VERSION
    _setup_log()

    logger.info("[E2E] Starting PB Studio E2E Render Test")
    logger.info("[E2E] Expected: 378 video segments + 1 audio track = 62.4 min")

    # GPU info cache (from main.py)
    try:
        from services.gpu_info import initialize_gpu_info_cache
        _gpu = initialize_gpu_info_cache()
        logger.info("[E2E] GPU: %s", _gpu.summary())
    except Exception as e:
        logger.warning("[E2E] GPU init: %s", e)

    # Create QApplication
    app = QApplication(sys.argv)

    # Task manager init (from main.py)
    from services.task_manager import GlobalTaskManager
    import services.task_manager as _task_manager_module
    _tm = GlobalTaskManager.instance()
    _task_manager_module.task_manager = _tm
    app.task_manager = _tm
    app.system_status = None

    # Theme
    from ui.theme import get_stylesheet
    app.setStyleSheet(get_stylesheet())

    # App icon
    from ui.app_icon import get_app_icon
    app.setWindowIcon(get_app_icon())

    # Database
    from database import Base, engine
    Base.metadata.create_all(engine)

    # Create main window
    logger.info("[E2E] Creating PBWindow...")
    from main import PBWindow
    try:
        window = PBWindow()
    except Exception as exc:
        logger.critical("[E2E] Window creation failed: %s", exc, exc_info=True)
        sys.exit(1)

    E2EState.window = window
    window.setWindowIcon(get_app_icon())
    window.show()

    # Run final_init (similar to main.py)
    def e2e_final_init():
        logger.info("[E2E] Running final initialization...")
        try:
            from services.ollama_service import OllamaService
            try:
                OllamaService.get().start()
            except Exception:
                pass

            # Startup checks
            from workers.startup import StartupCheckWorker
            from PySide6.QtCore import QThread

            worker = StartupCheckWorker()
            thread = QThread(window)
            worker.moveToThread(thread)

            def on_done(status):
                app.system_status = status
                logger.info("[E2E] Startup checks complete: %s", status.status_bar_text())
                window.timeline_view.load_from_db()
                thread.quit()

                # Schedule export automation 3 seconds after timeline loads
                logger.info("[E2E] Timeline loaded. Starting export in 3 seconds...")
                QTimer.singleShot(3000, run_export_automation)

            worker.finished.connect(on_done)
            worker.progress.connect(lambda msg: logger.info("[E2E] Startup: %s", msg))
            thread.started.connect(worker.run)

            # Keep refs
            window._e2e_startup_worker = worker
            window._e2e_startup_thread = thread

            thread.start()
        except Exception as e:
            logger.error("[E2E] Final init error: %s", e, exc_info=True)
            # Still try to export even if some init fails
            QTimer.singleShot(5000, run_export_automation)

    # Start final init after 500ms (like main.py)
    QTimer.singleShot(500, e2e_final_init)

    # Safety timeout: quit after 5 hours regardless
    QTimer.singleShot(5 * 3600 * 1000, lambda: (
        logger.error("[E2E] TIMEOUT: 5 hour safety limit reached"),
        write_result("TIMEOUT", "5 hour safety limit"),
        QApplication.instance().quit(),
    ))

    logger.info("[E2E] App event loop starting...")
    sys.exit(app.exec())
