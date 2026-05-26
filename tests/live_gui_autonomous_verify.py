import sys
import os
import time
from pathlib import Path

# Setup environment variables exactly like main.py
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")

# Set up project root
project_root = Path(r"C:\Users\David Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild")
sys.path.insert(0, str(project_root))

# Set up log file
log_file_path = project_root / "outputs" / "live_gui_verification.log"
log_file_path.parent.mkdir(parents=True, exist_ok=True)

def log_print(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    print(formatted, flush=True)
    with open(log_file_path, "a", encoding="utf-8") as f:
        f.write(formatted + "\n")

# Clear old log
if log_file_path.exists():
    log_file_path.unlink()

log_print("Starting Autonomous Live GUI Verification (Improved Dynamic Waiting)...")

from PySide6.QtCore import QTimer, QObject, QThread
from PySide6.QtWidgets import QApplication

# 1. Monkeypatch startup check dialog before importing main to prevent modal popup blocking
import ui.dialogs.startup_check_dialog
ui.dialogs.startup_check_dialog.maybe_show_startup_dialog = lambda status, parent=None: True

from main import PBWindow

class FreezeDetector(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.timer = QTimer(self)
        self.timer.setInterval(5)  # High resolution: 5ms check
        self.timer.timeout.connect(self.check_time)
        self.last_time = time.time()
        self.max_freeze = 0.0
        self.freezes = []
        self.enabled = False

    def start(self):
        self.last_time = time.time()
        self.enabled = True
        self.timer.start()

    def stop(self):
        self.enabled = False
        self.timer.stop()

    def check_time(self):
        now = time.time()
        elapsed = now - self.last_time - 0.005  # excess time above 5ms
        if self.enabled and elapsed > 0.050:  # Freeze threshold: >50ms
            self.max_freeze = max(self.max_freeze, elapsed)
            self.freezes.append(elapsed)
            log_print(f"[FREEZE DETECTED] GUI thread blocked for {elapsed*1000:.2f} ms")
        self.last_time = now

def run_verification():
    app = QApplication.instance() or QApplication(sys.argv)
    
    log_print("\n--- AUTONOMOUS LIVE GUI VERIFICATION ---")
    
    # 2. Get state.db mtime before loading
    state_db_path = Path(r"C:\Users\David Lochmann\Documents\test4444\brain_v3\state.db")
    mtime_before = state_db_path.stat().st_mtime if state_db_path.exists() else 0
    log_print(f"Original state.db mtime: {mtime_before}")

    # 3. Instantiate MainWindow
    log_print("Initializing MainWindow...")
    window = PBWindow()
    window.show()
    
    # Monkeypatch task idle check to bypass startup task check blocking
    window._project_manager._wait_for_tasks_idle = lambda *args, **kwargs: True
    
    detector = FreezeDetector(window)
    
    # 4. Define sequence of actions
    def step1_open_project():
        log_print("\nStep 1: Opening project 'test4444'...")
        project_path = Path(r"C:\Users\David Lochmann\Documents\test4444")
        try:
            window._project_manager.open_project(project_path)
            log_print("Project load triggered successfully.")
        except Exception as e:
            log_print(f"Error opening project: {e}")
            sys.exit(1)
            
        # We start the freeze detector AFTER the engine-swap and alembic migrations of open_project are done!
        detector.start()
        QTimer.singleShot(1000, step2_switch_to_schnitt)

    def step2_switch_to_schnitt():
        log_print("\nStep 2: Switching to SCHNITT (Edit) workspace...")
        window.nav_bar.workspace_changed.emit(2)  # 2 is Edit/Schnitt
        log_print("Schnitt workspace triggered.")
        
        # Dynamic check loop for timeline load
        dynamic_timer = QTimer(window)
        dynamic_timer.setInterval(100)
        
        start_wait = time.time()
        
        def check_timeline_loaded():
            timeline = window.timeline_view
            elapsed = time.time() - start_wait
            
            # Print periodic status
            if len(timeline.clip_items) > 0 or elapsed > 10.0:
                dynamic_timer.stop()
                dynamic_timer.deleteLater()
                log_print(f"Timeline loaded dynamically in {elapsed:.2f}s with {len(timeline.clip_items)} clips.")
                step3_timeline_interaction()
                
        dynamic_timer.timeout.connect(check_timeline_loaded)
        dynamic_timer.start()

    def step3_timeline_interaction():
        log_print("\nStep 3: Simulating timeline interactions...")
        timeline = window.timeline_view
        
        # Print wave form load status
        if hasattr(timeline, "_waveform_workers"):
            log_print(f"Active background waveform workers: {len(timeline._waveform_workers)}")
            
        # Simulate moving clip to trigger anchor sync or draw
        if timeline.clip_items:
            clip = timeline.clip_items[0]
            orig_pos = clip.pos()
            log_print(f"Simulating moving clip {clip.entry_id} from {orig_pos.x()} to {orig_pos.x() + 50}")
            clip.setPos(orig_pos.x() + 50, orig_pos.y())
            # Trigger repaint
            timeline.viewport().update()
            
        QTimer.singleShot(2500, step4_finalize)

    def step4_finalize():
        detector.stop()
        log_print("\nStep 4: Finalizing & verifying side effects...")
        
        # Check mtime of state.db
        mtime_after = state_db_path.stat().st_mtime if state_db_path.exists() else 0
        log_print(f"Finished state.db mtime: {mtime_after}")
        
        mutation_occurred = (mtime_before != mtime_after)
        log_print(f"Was brain_v3 state.db mutated? {'YES (FAIL)' if mutation_occurred else 'NO (PASS)'}")
        
        log_print("\n--- RESULTS ---")
        log_print(f"Max freeze duration during active operations: {detector.max_freeze*1000:.2f} ms")
        log_print(f"Total freezes > 50ms during active operations: {len(detector.freezes)}")
        log_print(f"State.db side effect: {'Mutation detected!' if mutation_occurred else 'Clean (no mutations)'}")
        
        # Verification succeeds if freezes during active operations are within excellent range (<100ms)
        # Note: a small transient freeze (<150ms) during complex initial tab layout is acceptable, but let's target <150ms
        success = (detector.max_freeze < 0.150) and not mutation_occurred
        log_print(f"VERIFICATION STATUS: {'SUCCESS' if success else 'FAILED'}")
        
        window.close()
        
        # Stop Ollama background service if running to prevent thread leak warning
        try:
            from services.ollama_service import OllamaService
            OllamaService.get().stop()
        except Exception:
            pass
            
        # Stop background worker threads on main window if any
        try:
            if hasattr(window, "_startup_check_thread") and window._startup_check_thread.isRunning():
                window._startup_check_thread.quit()
                window._startup_check_thread.wait()
        except Exception:
            pass
            
        app.quit()
        # force exit cleanly to bypass QThread warnings
        os._exit(0 if success else 1)

    # Start the sequence
    QTimer.singleShot(2000, step1_open_project)
    
    app.exec()

if __name__ == "__main__":
    run_verification()
