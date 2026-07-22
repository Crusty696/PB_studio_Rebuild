"""Geteilte Globals + Private-Helper fuer die edit-Actions (AUFRAEUM B1).

Verbatim aus services/actions/edit_actions.py extrahiert — kein Logik-Change.
`_main_thread_invoker` ist ein Singleton und existiert NUR hier.
"""

import logging
import threading
from pathlib import PurePosixPath, PureWindowsPath

from services.action_registry import action_registry

_logger = logging.getLogger(__name__)
_main_thread_invoker = None
_main_thread_invoker_lock = threading.Lock()


def _get_task_manager():
    """Gibt den TaskManager zurueck ohne QApplication-Kopplung."""
    from services.task_manager import GlobalTaskManager
    return GlobalTaskManager.instance()


def _validate_export_output_name(output_path: str | None) -> str:
    raw_name = (output_path or "output.mp4").strip() or "output.mp4"
    win_path = PureWindowsPath(raw_name)
    posix_path = PurePosixPath(raw_name)
    parts = set(win_path.parts) | set(posix_path.parts)
    if (
        win_path.is_absolute()
        or posix_path.is_absolute()
        or bool(win_path.drive)
        or ".." in parts
        or "\\" in raw_name
        or "/" in raw_name
        or win_path.name != raw_name
        or posix_path.name != raw_name
    ):
        raise ValueError("output_path darf nur ein Dateiname im Export-Ordner sein")
    return raw_name


# ── Hilfsfunktionen für GUI-Interaktion aus Hintergrund-Threads ─────────

def _get_main_window():
    """Findet das PBWindow-Hauptfenster über alle Top-Level-Widgets."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app:
        for widget in app.topLevelWidgets():
            if widget.__class__.__name__ == "PBWindow":
                return widget
    return None


def _get_project_manager():
    """Liefert die aktive ProjectManager-Instanz des Hauptfensters."""
    mw = _get_main_window()
    if mw and hasattr(mw, "_project_manager"):
        return mw._project_manager
    return None


def _get_main_thread_invoker(app):
    global _main_thread_invoker
    with _main_thread_invoker_lock:
        if _main_thread_invoker is None:
            from PySide6.QtCore import QObject, Qt, Signal, Slot

            class _MainThreadInvoker(QObject):
                call = Signal(object)

                def __init__(self):
                    super().__init__()
                    self.call.connect(
                        self._invoke,
                        Qt.ConnectionType.BlockingQueuedConnection,
                    )

                @Slot(object)
                def _invoke(self, payload):
                    callback, box = payload
                    try:
                        box["result"] = callback()
                    except Exception as exc:  # broad catch intentional: re-raised in caller thread
                        box["error"] = exc

            _main_thread_invoker = _MainThreadInvoker()
            _main_thread_invoker.moveToThread(app.thread())
        return _main_thread_invoker


def _run_on_main_thread(callback):
    from PySide6.QtCore import QThread
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None or QThread.currentThread() == app.thread():
        return callback()

    box = {}
    _get_main_thread_invoker(app).call.emit((callback, box))
    if "error" in box:
        raise box["error"]
    return box.get("result")
