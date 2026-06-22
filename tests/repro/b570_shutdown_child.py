"""Child process for B-570 shutdown lifecycle regression."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import time
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from PySide6.QtCore import QObject, QThread, QTimer, Slot
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox


class _StubbornWorker(QObject):
    @Slot()
    def run(self) -> None:
        time.sleep(30)

    def cancel(self) -> None:
        pass


def main() -> int:
    app = QApplication.instance() or QApplication([])

    import main as app_main
    from services.task_manager import GlobalTaskManager

    class _MinimalWindow(app_main.PBWindow):
        def __init__(self) -> None:
            QMainWindow.__init__(self)
            self._dirty = False
            self._active_threads = []
            self._active_workers = []

        def _save_window_state(self) -> None:
            pass

        def closeEvent(self, event) -> None:
            print("B570_CHILD_CLOSE_ENTER", flush=True)
            super().closeEvent(event)
            print(
                f"B570_CHILD_CLOSE_RETURN thread_running={thread.isRunning()}",
                flush=True,
            )

    manager = GlobalTaskManager.instance()
    thread = QThread()
    worker = _StubbornWorker()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)

    task = manager.create_task("B-570 cancelled-but-running")
    task.worker = worker
    task.thread = thread
    task.status = "cancelled"
    thread.start()
    print(f"B570_CHILD_THREAD_STARTED running={thread.isRunning()}", flush=True)

    ollama = MagicMock()
    with (
        patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes),
        patch.object(app_main.OllamaService, "get", return_value=ollama),
        patch("services.model_manager.ModelManager", return_value=MagicMock()),
        patch("ui.controllers.convert.shutdown_convert_db_pool", return_value=True),
        patch("torch.cuda.is_available", return_value=False),
    ):
        window = _MinimalWindow()
        window.show()
        QTimer.singleShot(50, window.close)
        QTimer.singleShot(12_000, app.quit)
        print("B570_CHILD_EVENTLOOP_START", flush=True)
        app.exec()
        print(f"B570_CHILD_EVENTLOOP_RETURN thread_running={thread.isRunning()}", flush=True)

    if thread.isRunning():
        print("B570_CHILD_WAITING_HARD_EXIT", flush=True)
        time.sleep(3)
        print("B570_CHILD_HARD_EXIT_MISSING", flush=True)
        return 2

    print("B570_CHILD_EXIT_OK", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
