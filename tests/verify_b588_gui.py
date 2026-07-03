import sys
import os
import time
from pathlib import Path

# Environment setup
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")
os.environ["QT_QPA_PLATFORM"] = "offscreen"  # Headless run

project_root = Path(r"C:\Users\David_Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild")
sys.path.insert(0, str(project_root))

log_file_path = project_root / "outputs" / "verify_b588_gui.log"
log_file_path.parent.mkdir(parents=True, exist_ok=True)

def log_print(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    print(formatted, flush=True)
    with open(log_file_path, "a", encoding="utf-8") as f:
        f.write(formatted + "\n")

if log_file_path.exists():
    log_file_path.unlink()

log_print("Starting GUI Verification for B-588 (Optimized Timing)...")

from PySide6.QtCore import QTimer, QObject
from PySide6.QtWidgets import QApplication

# Monkeypatch startup check dialog
import ui.dialogs.startup_check_dialog
ui.dialogs.startup_check_dialog.maybe_show_startup_dialog = lambda status, parent=None: True

from main import PBWindow

class FreezeDetector(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.timer = QTimer(self)
        self.timer.setInterval(5)
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
        elapsed = now - self.last_time - 0.005
        if self.enabled and elapsed > 0.050:  # >50ms freeze
            self.max_freeze = max(self.max_freeze, elapsed)
            self.freezes.append(elapsed)
            log_print(f"[FREEZE DETECTED] GUI thread blocked for {elapsed*1000:.2f} ms")
        self.last_time = now

def run_verification():
    app = QApplication.instance() or QApplication(sys.argv)
    log_print("\n--- B-588 GUI VERIFICATION ---")
    
    log_print("Initializing MainWindow...")
    window = PBWindow()
    window.show()
    
    window._project_manager._wait_for_tasks_idle = lambda *args, **kwargs: True
    detector = FreezeDetector(window)

    def step1_open_project():
        log_print("\nStep 1: Opening project 'E2E_20260625_quick'...")
        project_path = project_root / "projects" / "E2E_20260625_quick"
        try:
            window._project_manager.open_project(project_path)
            log_print("Project load triggered.")
        except Exception as e:
            log_print(f"Error opening project: {e}")
            sys.exit(1)
        QTimer.singleShot(1000, step2_switch_to_schnitt)

    def step2_switch_to_schnitt():
        log_print("\nStep 2: Switching to SCHNITT workspace...")
        # Start freeze detector AFTER project load is completed
        detector.start()
        window.nav_bar.workspace_changed.emit(2)  # 2 is Edit/Schnitt
        log_print("Schnitt workspace active.")
        QTimer.singleShot(1000, step3_simulate_clicks)

    def step3_simulate_clicks():
        log_print("\nStep 3: Simulating clicks on tabs...")
        # Switch tabs multiple times to trigger event loop notifications
        # 0: PROJEKT, 1: MATERIAL & ANALYSE, 2: SCHNITT, 3: EXPORT
        for tab_idx in [1, 2, 3, 2, 1, 0]:
            log_print(f"Clicking workspace tab {tab_idx}...")
            window.nav_bar.workspace_changed.emit(tab_idx)
            app.processEvents()
            time.sleep(0.1)
        QTimer.singleShot(1000, step4_finalize)

    def step4_finalize():
        detector.stop()
        log_print("\nStep 4: Finalizing...")
        log_print(f"Max freeze duration during active navigation: {detector.max_freeze*1000:.2f} ms")
        log_print(f"Total freezes > 50ms: {len(detector.freezes)}")
        
        # We target max freeze under 250ms for normal navigation clicks
        success = (detector.max_freeze < 0.250)
        log_print(f"VERIFICATION STATUS: {'SUCCESS' if success else 'FAILED'}")
        
        window.close()
        app.quit()
        os._exit(0 if success else 1)

    QTimer.singleShot(1000, step1_open_project)
    app.exec()

if __name__ == "__main__":
    run_verification()
