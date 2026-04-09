
import threading
import logging
from PySide6.QtCore import QObject, Signal
from services.startup_checks import check_system, SystemStatus

logger = logging.getLogger(__name__)

class StartupCheckWorker(QObject):
    """Hintergrund-Worker für die Systemprüfung und DB-Init beim Start (Fix F-030)."""
    finished = Signal(object)  # SystemStatus
    progress = Signal(str)

    def run(self):
        try:
            self.progress.emit("Initialisiere Datenbank...")
            # F-031 Fix: DB-Init im Hintergrund um Main-Thread zu entlasten
            from database import init_db
            init_db()
            
            self.progress.emit("Initialisiere KI-Umgebung (torch)...")
            status = check_system()
            self.finished.emit(status)
        except Exception as e:
            logger.error("Kritischer Fehler bei Systemprüfung: %s", e, exc_info=True)
            # Fallback Status mit Fehler
            err_status = SystemStatus()
            err_status.errors.append(f"Systemcheck abgestürzt: {e}")
            self.finished.emit(err_status)
