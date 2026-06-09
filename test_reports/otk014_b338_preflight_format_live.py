from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = Path(r"C:\Users\David Lochmann\Downloads\video\test55655")
OUT_JSON = ROOT / "test_reports" / "otk014_b338_preflight_format_live_20260609.json"
OUT_PNG = ROOT / "test_reports" / "otk014_b338_preflight_format_live_20260609.png"


def main() -> int:
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    os.environ.setdefault("OMP_NUM_THREADS", "4")
    os.environ.setdefault("MKL_NUM_THREADS", "4")
    sys.path.insert(0, str(ROOT))

    from PySide6.QtCore import QObject, QTimer, Signal
    from PySide6.QtWidgets import QApplication

    import ui.dialogs.startup_check_dialog
    ui.dialogs.startup_check_dialog.maybe_show_startup_dialog = lambda status, parent=None: True

    from main import PBWindow
    import services.ingest_service as ingest_service
    import ui.controllers.convert as convert_mod

    app = QApplication.instance() or QApplication(sys.argv)
    window = PBWindow()
    window.show()
    window.resize(1600, 950)
    app.processEvents()

    captured: dict = {}

    class _FakeWorker(QObject):
        progress = Signal(int, str)
        finished = Signal(int, int)
        error = Signal(str)

        def __init__(self, videos, resolution, fps, vcodec, ext):
            super().__init__()
            captured.update(
                {
                    "video_count": len(videos),
                    "resolution": resolution,
                    "fps": fps,
                    "vcodec": vcodec,
                    "ext": ext,
                }
            )

    def _fake_start(worker):
        captured["worker_class"] = type(worker).__name__
        return None

    result = {
        "project": str(PROJECT),
        "ok": False,
        "screenshot": str(OUT_PNG),
    }

    def finish() -> None:
        OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
        window.close()
        app.quit()

    def run() -> None:
        try:
            if PROJECT.exists():
                window._project_manager._wait_for_tasks_idle = lambda *args, **kwargs: True
                window._project_manager.open_project(PROJECT)
            window.nav_bar.set_workspace(1)
            window.workspace_setup._on_workspace_changed(1)
            app.processEvents()

            window.convert_resolution.setCurrentText("3840x2160 (4K)")
            window.convert_fps.setCurrentText("50 fps")
            window.convert_format.setCurrentText("mp4 (H.265/HEVC)")
            window.btn_standardize_all.setEnabled(True)
            app.processEvents()

            original_get_all_video = ingest_service.get_all_video
            original_worker = convert_mod.BatchConvertWorker
            original_start = window.worker_dispatcher._start_worker_thread
            ingest_service.get_all_video = lambda: [object(), object()]
            convert_mod.BatchConvertWorker = _FakeWorker
            window.worker_dispatcher._start_worker_thread = _fake_start
            try:
                window.btn_standardize_all.click()
                app.processEvents()
            finally:
                ingest_service.get_all_video = original_get_all_video
                convert_mod.BatchConvertWorker = original_worker
                window.worker_dispatcher._start_worker_thread = original_start

            result.update(
                {
                    "format_group_visible": window._convert_ws.format_group.isVisible(),
                    "format_group_parent": type(window._convert_ws.format_group.parent()).__name__,
                    "resolution_text": window.convert_resolution.currentText(),
                    "fps_text": window.convert_fps.currentText(),
                    "format_text": window.convert_format.currentText(),
                    "button_visible": window.btn_standardize_all.isVisible(),
                    "captured": dict(captured),
                }
            )
            result["ok"] = (
                result["format_group_visible"]
                and result["button_visible"]
                and captured.get("resolution") == "3840x2160"
                and captured.get("fps") == "50"
                and captured.get("vcodec") == "hevc_nvenc"
                and captured.get("ext") == ".mp4"
            )
            OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
            window.grab().save(str(OUT_PNG))
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            finish()

    QTimer.singleShot(1000, run)
    QTimer.singleShot(120000, app.quit)
    app.exec()
    print(json.dumps(result, indent=2))
    sys.stdout.flush()
    os._exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    raise SystemExit(main())
