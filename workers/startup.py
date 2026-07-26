
import threading
import logging
from PySide6.QtCore import QObject, Signal
from services.startup_checks import check_system, SystemStatus

logger = logging.getLogger(__name__)

class StartupCheckWorker(QObject):
    """Hintergrund-Worker für die Systemprüfung und DB-Init beim Start (Fix F-030).

    ``init_database`` steuert, ob der Worker ``init_db()`` selbst ausfuehrt.
    Statusaufnahme 2026-07-26: ``main.py`` migriert bereits synchron ueber
    ``run_database_bootstrap()`` VOR dem Fenster (das muss so bleiben, weil
    PBWindow sofort ORM-Queries fahrt). Der zusaetzliche Worker-Aufruf war
    damit ein zweiter Durchlauf derselben Alembic-Migrationen im
    Hintergrund-Thread, parallel zu den ersten UI-DB-Zugriffen — im Boot-Log
    stand "Alembic-Migrationen abgeschlossen (head)." zweimal.
    ``main.py`` uebergibt daher ``init_database=False``.

    Standalone-Aufrufer ohne eigenen Bootstrap (z.B.
    ``scripts/diag/e2e_render_test.py``) behalten den Default ``True``.
    """
    finished = Signal(object)  # SystemStatus
    progress = Signal(str)

    def __init__(self, init_database: bool = True, parent=None):
        super().__init__(parent)
        self._init_database = init_database

    def run(self):
        try:
            if self._init_database:
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
