"""B-615 regression tests: closeEvent must prompt on unsaved changes.

Live-Sichtung 2026-07-11 00:23:33: PBWindow closed cleanly WITHOUT the
"Ungespeicherte Änderungen"-prompt although the title showed 'test33 *'
(window._dirty=True on the 00:22:46 screenshot). These tests pin the
expected behavior of the dirty-check path in PBWindow.closeEvent:

1. dirty + user answers No  -> event ignored, window stays open,
   no shutdown side effects.
2. dirty + user answers Yes -> close proceeds.
3. clean                    -> no prompt at all.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox, QTextEdit


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_window(monkeypatch):
    import main
    from PySide6.QtWidgets import QWidget

    class FakeResourceMonitor(QWidget):
        def stop(self) -> None:
            pass

    monkeypatch.setattr(main, "ResourceMonitorWidget", FakeResourceMonitor)
    monkeypatch.setattr(main.PBWindow, "_boot_brain_v3_services", lambda self: None)
    monkeypatch.setattr(main.WorkspaceSetupController, "_create_workspaces", lambda self: None)
    monkeypatch.setattr(main.WorkspaceSetupController, "_restore_window_state", lambda self: None)
    monkeypatch.setattr(main.MediaTableController, "_refresh_media_table", lambda self: None)
    monkeypatch.setattr(main.MediaTableController, "_refresh_director_combos", lambda self: None)
    monkeypatch.setattr(main.PanelSetupController, "setup_task_dock", lambda self: None)
    monkeypatch.setattr(
        main.PanelSetupController,
        "setup_console",
        lambda self: setattr(self.window, "console_text", QTextEdit()),
    )
    monkeypatch.setattr(main.PanelSetupController, "setup_chat_dock", lambda self: None)
    monkeypatch.setattr(main.PanelSetupController, "setup_analysis_completion_bridge", lambda self: None)

    window = main.PBWindow()
    return window


def test_close_dirty_prompts_and_no_keeps_window_open(monkeypatch) -> None:
    app = _ensure_qapp()
    window = _make_window(monkeypatch)
    app.processEvents()

    window._dirty = True

    calls: list[tuple] = []

    def fake_question(parent, title, text, *args, **kwargs):
        calls.append((title, text))
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake_question))

    closed = window.close()
    app.processEvents()

    assert calls, (
        "B-615: closeEvent ran without the unsaved-changes prompt "
        "although window._dirty was True."
    )
    assert closed is False, (
        "B-615: answering 'No' on the unsaved-changes prompt must abort "
        "the close (event.ignore)."
    )

    # Cleanup: allow the window to close for teardown.
    window._dirty = False
    window.close()
    app.processEvents()


def test_close_dirty_prompt_yes_proceeds(monkeypatch) -> None:
    app = _ensure_qapp()
    window = _make_window(monkeypatch)
    app.processEvents()

    window._dirty = True

    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )

    closed = window.close()
    app.processEvents()

    assert closed is True, (
        "B-615: answering 'Yes' must let the close proceed."
    )


def test_close_clean_never_prompts(monkeypatch) -> None:
    app = _ensure_qapp()
    window = _make_window(monkeypatch)
    app.processEvents()

    assert window._dirty is False

    calls: list[tuple] = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *a, **k: calls.append(a) or QMessageBox.StandardButton.Yes),
    )

    closed = window.close()
    app.processEvents()

    assert closed is True
    assert not any("Ungespeicherte" in str(c) for c in calls), (
        "closeEvent must not show the unsaved-changes prompt when clean."
    )
