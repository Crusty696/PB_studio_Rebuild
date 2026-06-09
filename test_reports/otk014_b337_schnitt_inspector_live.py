from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = Path(r"C:\Users\David Lochmann\Downloads\video\test55655")
OUT_JSON = ROOT / "test_reports" / "otk014_b337_schnitt_inspector_live_20260609.json"
OUT_PNG = ROOT / "test_reports" / "otk014_b337_schnitt_inspector_live_20260609.png"


def main() -> int:
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    os.environ.setdefault("OMP_NUM_THREADS", "4")
    os.environ.setdefault("MKL_NUM_THREADS", "4")
    sys.path.insert(0, str(ROOT))

    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    import ui.dialogs.startup_check_dialog
    ui.dialogs.startup_check_dialog.maybe_show_startup_dialog = lambda status, parent=None: True

    from main import PBWindow

    if not PROJECT.exists():
        raise RuntimeError(f"project missing: {PROJECT}")

    app = QApplication.instance() or QApplication(sys.argv)
    window = PBWindow()
    window.show()
    window.resize(1600, 950)
    app.processEvents()

    result: dict = {
        "project": str(PROJECT),
        "ok": False,
        "timeline_clips": 0,
        "inspector_visible": False,
        "brightness_visible": False,
        "contrast_visible": False,
        "crossfade_visible": False,
        "screenshot": str(OUT_PNG),
    }

    def fail(message: str) -> None:
        result["error"] = message
        OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
        window.close()
        app.quit()

    def wait_until(predicate, timeout_s: float, poll_ms: int = 100) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate():
                return True
            QTest.qWait(poll_ms)
        app.processEvents()
        return bool(predicate())

    def run() -> None:
        try:
            window._project_manager._wait_for_tasks_idle = lambda *args, **kwargs: True
            window._project_manager.open_project(PROJECT)
            app.processEvents()
            window.nav_bar.set_workspace(2)
            window.workspace_setup._on_workspace_changed(2)
            app.processEvents()

            timeline = window.timeline_view
            if not wait_until(lambda: len(getattr(timeline, "clip_items", [])) > 0, 15.0):
                fail("timeline clips did not load")
                return
            result["timeline_clips"] = len(timeline.clip_items)

            clip = timeline.clip_items[0]
            center = clip.sceneBoundingRect().center()
            pos = timeline.mapFromScene(center)
            QTest.mouseClick(timeline.viewport(), Qt.MouseButton.LeftButton, pos=pos)
            app.processEvents()

            inspector = window._schnitt_ws.editor_view.inspector_panel
            if not wait_until(lambda: getattr(inspector, "_current_entry_id", None) is not None, 5.0):
                fail("inspector did not receive selected timeline entry")
                return

            result["selected_entry_id"] = int(inspector._current_entry_id)
            result["inspector_visible"] = inspector.isVisible()
            result["brightness_visible"] = inspector._brightness_spin.isVisible()
            result["contrast_visible"] = inspector._contrast_spin.isVisible()
            result["crossfade_visible"] = inspector._crossfade_spin.isVisible()
            result["brightness_value"] = float(inspector._brightness_spin.value())
            result["contrast_value"] = float(inspector._contrast_spin.value())
            result["crossfade_value"] = float(inspector._crossfade_spin.value())
            result["ok"] = all(
                result[key]
                for key in (
                    "inspector_visible",
                    "brightness_visible",
                    "contrast_visible",
                    "crossfade_visible",
                )
            )
            OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
            window.grab().save(str(OUT_PNG))
            OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
            OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
        finally:
            window.close()
            app.quit()

    QTimer.singleShot(1000, run)
    QTimer.singleShot(120000, app.quit)
    app.exec()
    print(json.dumps(result, indent=2))
    sys.stdout.flush()
    os._exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    raise SystemExit(main())
