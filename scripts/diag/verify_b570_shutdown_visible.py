"""B-570 visible shutdown verifier.

Launches a real visible Qt window with PBWindow.closeEvent, creates a
cancelled-but-still-running QThread, closes the window, clicks the real
"running tasks" confirmation dialog via pywinauto, and verifies that the child
process exits instead of staying headless.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import MagicMock, patch

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = REPO_ROOT / "tests" / "qa_artifacts"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def _emit(event: str, **data: object) -> None:
    payload = {"event": event, **data}
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def _pid_is_alive(pid: int) -> bool:
    out = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
        capture_output=True,
        text=True,
        check=False,
    )
    return str(pid) in (out.stdout or "")


def _child() -> int:
    sys.path.insert(0, str(REPO_ROOT))

    from PySide6.QtCore import QObject, QThread, QTimer, Slot
    from PySide6.QtWidgets import QApplication, QMainWindow

    class _StubbornWorker(QObject):
        @Slot()
        def run(self) -> None:
            time.sleep(30)

        def cancel(self) -> None:
            _emit("worker_cancel_called")

    app = QApplication.instance() or QApplication([])

    import main as app_main
    from services.task_manager import GlobalTaskManager

    thread = QThread()
    worker = _StubbornWorker()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)

    class _VisibleWindow(app_main.PBWindow):
        def __init__(self) -> None:
            QMainWindow.__init__(self)
            self._dirty = False
            self._active_threads = []
            self._active_workers = []
            self.setWindowTitle("PB_studio B570 Visible Shutdown")
            self.resize(640, 360)

        def _save_window_state(self) -> None:
            pass

        def closeEvent(self, event) -> None:
            _emit("close_event_enter", thread_running=thread.isRunning())
            super().closeEvent(event)
            _emit("close_event_return", thread_running=thread.isRunning())

    manager = GlobalTaskManager.instance()
    task = manager.create_task("B-570 visible cancelled-but-running")
    task.worker = worker
    task.thread = thread
    task.status = "cancelled"
    thread.start()
    _emit("thread_started", thread_running=thread.isRunning())

    with (
        patch.object(app_main.OllamaService, "get", return_value=MagicMock()),
        patch("services.model_manager.ModelManager", return_value=MagicMock()),
        patch("ui.controllers.convert.shutdown_convert_db_pool", return_value=True),
        patch("torch.cuda.is_available", return_value=False),
    ):
        window = _VisibleWindow()
        window.show()
        _emit("window_shown", title=window.windowTitle())
        QTimer.singleShot(300, window.close)
        QTimer.singleShot(20_000, app.quit)
        app.exec()
        _emit("event_loop_return", thread_running=thread.isRunning())

    if thread.isRunning():
        _emit("waiting_for_hard_exit")
        time.sleep(3)
        _emit("hard_exit_missing")
        return 2

    _emit("exit_ok")
    return 0


def _parent(timeout_s: float) -> int:
    out_path = ARTIFACT_DIR / "b570_visible_shutdown_stdout.jsonl"
    err_path = ARTIFACT_DIR / "b570_visible_shutdown_stderr.log"
    env = os.environ.copy()
    env.pop("QT_QPA_PLATFORM", None)
    env["PYTHONUNBUFFERED"] = "1"

    with out_path.open("w", encoding="utf-8") as out_fh, err_path.open("w", encoding="utf-8") as err_fh:
        proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--child"],
            cwd=str(REPO_ROOT),
            env=env,
            stdout=out_fh,
            stderr=err_fh,
        )

    clicked = False
    clicked_button = ""
    dialog_title = ""
    dialog_texts: list[str] = []
    click_error = ""
    deadline = time.monotonic() + timeout_s
    try:
        from pywinauto import Desktop

        while time.monotonic() < deadline and proc.poll() is None:
            windows = Desktop(backend="uia").windows()
            for win in windows:
                title = win.window_text() or ""
                if "Laufende Tasks" not in title and "PB Studio" not in title and "PB_studio" not in title:
                    continue
                texts = " ".join((child.window_text() or "") for child in win.descendants())
                if "Trotzdem beenden" not in texts and "laufen noch" not in texts:
                    continue
                dialog_title = title
                dialog_texts = [child.window_text() or "" for child in win.descendants()]
                try:
                    button = win.child_window(
                        title_re=".*(Yes|Ja|&Yes|&Ja).*",
                        control_type="Button",
                    )
                    clicked_button = button.window_text() or "<empty affirmative>"
                    button.click_input()
                except Exception:
                    buttons = [b for b in win.descendants(control_type="Button") if b.is_enabled()]
                    if not buttons:
                        raise
                    affirmative = None
                    for button in buttons:
                        text = button.window_text() or ""
                        if text.strip().lower().replace("&", "") in {"yes", "ja"}:
                            affirmative = button
                            break
                    if affirmative is None:
                        raise RuntimeError(
                            "no affirmative button found; buttons="
                            + repr([b.window_text() for b in buttons])
                        )
                    clicked_button = affirmative.window_text() or "<empty affirmative fallback>"
                    affirmative.click_input()
                clicked = True
                break
            if clicked:
                break
            time.sleep(0.2)
    except Exception as exc:  # noqa: BLE001 - verifier must report harness failure.
        click_error = f"{type(exc).__name__}: {exc}"

    try:
        returncode = proc.wait(timeout=max(1.0, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False)
        returncode = None

    alive_after = _pid_is_alive(proc.pid)
    stdout = out_path.read_text(encoding="utf-8", errors="replace") if out_path.exists() else ""
    stderr = err_path.read_text(encoding="utf-8", errors="replace") if err_path.exists() else ""
    result = {
        "ok": bool(clicked and returncode == 0 and not alive_after and "hard_exit_missing" not in stdout),
        "pid": proc.pid,
        "clicked_dialog": clicked,
        "clicked_button": clicked_button,
        "dialog_title": dialog_title,
        "dialog_texts": dialog_texts,
        "click_error": click_error,
        "returncode": returncode,
        "alive_after": alive_after,
        "stdout_path": str(out_path),
        "stderr_path": str(err_path),
        "stdout_tail": stdout.splitlines()[-20:],
        "stderr_tail": stderr.splitlines()[-20:],
    }
    result_path = ARTIFACT_DIR / "b570_visible_shutdown_result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--timeout-s", type=float, default=45.0)
    args = parser.parse_args()
    if args.child:
        return _child()
    return _parent(args.timeout_s)


if __name__ == "__main__":
    raise SystemExit(main())
