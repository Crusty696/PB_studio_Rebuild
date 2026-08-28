"""STAB-5 Controls #48-#56: SettingsDialog-Widgets elementgenau belegen.

Isolation (keine Host-Writes, kein Netz, keine Threads):
- ui.dialogs.settings_dialog bindet get_settings_store/get_ollama_settings/
  save_ollama_settings im eigenen Modul-Namespace -> dort patchen, NICHT in
  services.settings_store.
- ShortcutEditorTab holt get_shortcut_manager function-level -> Patch auf
  ui.shortcut_manager greift.
- run_worker wird durch synchronen Recorder ersetzt -> kein QThread, kein
  Ollama-HTTP; Payload wird im Test manuell geliefert.
- Modale Sub-Dialoge (_KeyCaptureDialog, ModelManagerDialog,
  StorageBrowserDialog) werden durch Recording-Fakes ersetzt.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QPushButton,
)


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


class _FakeStore:
    """Ersatz fuer SettingsStore — schreibt nie auf Disk."""

    def __init__(self) -> None:
        self.nested_writes: list[tuple[tuple, object]] = []

    def get_nested(self, *path, default=None):
        return default

    def set_nested(self, *path, value=None):
        self.nested_writes.append((path, value))

    def get_ollama_settings(self):
        return {"enabled": True, "url": "http://localhost:11434", "model": "gemma:2b"}


class _FakeShortcutManager:
    """Ersatz fuer das ShortcutManager-Singleton — kein Settings-Write."""

    def __init__(self) -> None:
        self.save_calls = 0
        self.set_calls: list[tuple[str, str]] = []

    def display_text(self, action_id: str) -> str:
        from ui.shortcut_manager import ACTIONS

        return ACTIONS[action_id][2]

    def set_sequence(self, action_id: str, seq: QKeySequence) -> None:
        self.set_calls.append((action_id, seq.toString()))

    def save(self) -> None:
        self.save_calls += 1


class _FakeThread:
    def isRunning(self) -> bool:
        return False


class _FakeKeyCapture:
    """Ersatz fuer _KeyCaptureDialog: liefert sofort F5 als Accepted."""

    def __init__(self, action_name: str, parent=None) -> None:
        self.action_name = action_name

    def exec(self):
        return QDialog.DialogCode.Accepted

    def captured_sequence(self):
        return QKeySequence("F5")


class _FakeModelManagerDialog:
    calls: list = []

    def __init__(self, parent=None, ollama_url=None) -> None:
        type(self).calls.append(("init", parent, ollama_url))

    def exec(self):
        type(self).calls.append(("exec",))
        return 0


class _FakeStorageBrowserDialog:
    calls: list = []

    def __init__(self, parent=None) -> None:
        type(self).calls.append(("init", parent))

    def exec(self):
        type(self).calls.append(("exec",))
        return 0


def _make_dialog(monkeypatch):
    app = _qapp()
    import ui.dialogs.settings_dialog as sd
    import ui.shortcut_manager as smod

    store = _FakeStore()
    sm = _FakeShortcutManager()
    saved: list[tuple] = []
    worker_calls: list[dict] = []

    monkeypatch.setattr(sd, "get_settings_store", lambda: store)
    monkeypatch.setattr(sd, "get_ollama_settings", store.get_ollama_settings)
    monkeypatch.setattr(
        sd, "save_ollama_settings",
        lambda enabled, url, model: saved.append((enabled, url, model)),
    )
    monkeypatch.setattr(smod, "get_shortcut_manager", lambda: sm)

    def _fake_run_worker(owner, worker, on_finish=None, on_error=None):
        worker_calls.append(
            {"worker": worker, "on_finish": on_finish, "on_error": on_error}
        )
        return _FakeThread()

    monkeypatch.setattr(sd, "run_worker", _fake_run_worker)

    dlg = sd.SettingsDialog()
    dlg.show()
    app.processEvents()
    ctx = {
        "app": app,
        "store": store,
        "sm": sm,
        "saved": saved,
        "worker_calls": worker_calls,
    }
    return dlg, ctx


def _teardown(dlg, app) -> None:
    dlg.close()
    dlg.deleteLater()
    app.processEvents()


def _single_button(dlg, text: str) -> QPushButton:
    buttons = [b for b in dlg.findChildren(QPushButton) if b.text() == text]
    assert len(buttons) == 1
    button = buttons[0]
    assert button.isVisibleTo(dlg) is True
    assert button.isEnabled() is True
    return button


def _single_checkbox(dlg, text: str) -> QCheckBox:
    boxes = [c for c in dlg.findChildren(QCheckBox) if c.text() == text]
    assert len(boxes) == 1
    box = boxes[0]
    assert box.isVisibleTo(dlg) is True
    assert box.isEnabled() is True
    return box


def _single_combo(dlg) -> QComboBox:
    combos = dlg.findChildren(QComboBox)
    assert len(combos) == 1
    combo = combos[0]
    assert combo.isVisibleTo(dlg) is True
    assert combo.isEnabled() is True
    return combo


def _goto_tab(dlg, index: int, app) -> None:
    dlg._tabs.setCurrentIndex(index)
    app.processEvents()


def test_48_btn_edit_records_new_shortcut_into_pending(monkeypatch) -> None:
    """Control #48: 'Bearbeiten' -> KeyCapture -> _pending + Tabellen-Zelle."""
    dlg, ctx = _make_dialog(monkeypatch)
    try:
        import ui.dialogs.settings_dialog as sd

        monkeypatch.setattr(sd, "_KeyCaptureDialog", _FakeKeyCapture)
        _goto_tab(dlg, 2, ctx["app"])
        tab = dlg._shortcut_tab
        tab._table.setCurrentCell(0, 0)
        action_id = tab._table.item(0, 0).data(Qt.ItemDataRole.UserRole)

        button = _single_button(dlg, "Bearbeiten")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        ctx["app"].processEvents()

        assert tab._pending[action_id].toString() == "F5"
        assert tab._table.item(0, 2).text() == "F5"
        assert ctx["sm"].set_calls == []
        assert ctx["sm"].save_calls == 0
    finally:
        _teardown(dlg, ctx["app"])


def test_49_btn_reset_fills_pending_with_defaults(monkeypatch) -> None:
    """Control #49: 'Alle zurücksetzen' -> _pending = Defaults, kein Save."""
    dlg, ctx = _make_dialog(monkeypatch)
    try:
        from ui.shortcut_manager import ACTIONS

        _goto_tab(dlg, 2, ctx["app"])
        button = _single_button(dlg, "Alle zurücksetzen")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        ctx["app"].processEvents()

        tab = dlg._shortcut_tab
        assert set(tab._pending) == set(ACTIONS)
        for action_id, (_n, _d, default) in ACTIONS.items():
            assert tab._pending[action_id].toString() == QKeySequence(default).toString()
        assert ctx["sm"].save_calls == 0
    finally:
        _teardown(dlg, ctx["app"])


def test_50_chk_enabled_click_disables_dependent_widgets(monkeypatch) -> None:
    """Control #50: Checkbox-Klick -> _on_enabled_toggled schaltet 4 Widgets."""
    dlg, ctx = _make_dialog(monkeypatch)
    try:
        chk = _single_checkbox(dlg, "Ollama als LLM-Backend nutzen")
        assert chk.isChecked() is True
        assert dlg._txt_url.isEnabled() is True

        QTest.mouseClick(chk, Qt.MouseButton.LeftButton)
        ctx["app"].processEvents()

        assert chk.isChecked() is False
        assert dlg._txt_url.isEnabled() is False
        assert dlg._btn_test.isEnabled() is False
        assert dlg._cmb_model.isEnabled() is False
        assert dlg._btn_refresh.isEnabled() is False

        QTest.mouseClick(chk, Qt.MouseButton.LeftButton)
        ctx["app"].processEvents()
        assert chk.isChecked() is True
        assert dlg._btn_test.isEnabled() is True
    finally:
        _teardown(dlg, ctx["app"])


def test_51_btn_test_starts_worker_and_updates_status(monkeypatch) -> None:
    """Control #51: 'Verbindung testen' -> Worker mit URL, Status, Modelle."""
    dlg, ctx = _make_dialog(monkeypatch)
    try:
        button = _single_button(dlg, "Verbindung testen")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        ctx["app"].processEvents()

        assert len(ctx["worker_calls"]) == 1
        call = ctx["worker_calls"][0]
        assert call["worker"].url == "http://localhost:11434"
        assert dlg._btn_test.isEnabled() is False
        assert dlg._lbl_status.text() == "Teste Verbindung..."

        call["on_finish"]((True, "Verbunden! 2 Modelle.", ["gemma:2b", "llama3"]))
        ctx["app"].processEvents()

        assert dlg._btn_test.isEnabled() is True
        assert dlg._lbl_status.text() == "Verbunden! 2 Modelle."
        models = [dlg._cmb_model.itemText(i) for i in range(dlg._cmb_model.count())]
        assert models == ["gemma:2b", "llama3"]
        assert dlg._cmb_model.currentText() == "gemma:2b"
        assert dlg._test_thread is None and dlg._test_worker is None
    finally:
        _teardown(dlg, ctx["app"])


def test_52_cmb_model_typed_text_reaches_commit(monkeypatch) -> None:
    """Control #52: ComboBox-Eingabe -> Modell landet in save_ollama_settings."""
    dlg, ctx = _make_dialog(monkeypatch)
    try:
        combo = _single_combo(dlg)
        assert combo.isEditable() is True

        combo.lineEdit().selectAll()
        QTest.keyClicks(combo.lineEdit(), "phi3:mini")
        ctx["app"].processEvents()
        assert combo.currentText() == "phi3:mini"

        QTest.mouseClick(dlg._btn_ok, Qt.MouseButton.LeftButton)
        ctx["app"].processEvents()
        assert len(ctx["worker_calls"]) == 1
        assert dlg._pending_save == (True, "http://localhost:11434", "phi3:mini")
        assert dlg._btn_ok.isEnabled() is False

        ctx["worker_calls"][0]["on_finish"]((False, "nicht erreichbar", []))
        ctx["app"].processEvents()

        assert ctx["saved"] == [(True, "http://localhost:11434", "phi3:mini")]
        assert dlg.result() == QDialog.DialogCode.Accepted
    finally:
        _teardown(dlg, ctx["app"])


def test_53_btn_refresh_delegates_to_test_handler(monkeypatch) -> None:
    """Control #53: '↻' -> _on_refresh_clicked delegiert an _on_test_clicked."""
    dlg, ctx = _make_dialog(monkeypatch)
    try:
        dlg._txt_url.setText("http://myhost:11434")
        button = _single_button(dlg, "↻")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        ctx["app"].processEvents()

        assert len(ctx["worker_calls"]) == 1
        assert ctx["worker_calls"][0]["worker"].url == "http://myhost:11434"
        assert dlg._lbl_status.text() == "Teste Verbindung..."
        assert dlg._btn_test.isEnabled() is False
    finally:
        _teardown(dlg, ctx["app"])


def test_54_btn_model_manager_opens_dialog_with_url(monkeypatch) -> None:
    """Control #54: '⊞ Modell-Manager öffnen' -> ModelManagerDialog.exec()."""
    dlg, ctx = _make_dialog(monkeypatch)
    try:
        _FakeModelManagerDialog.calls = []
        monkeypatch.setattr(
            "ui.dialogs.model_manager_dialog.ModelManagerDialog",
            _FakeModelManagerDialog,
        )
        dlg._txt_url.setText("http://myhost:11434")
        button = _single_button(dlg, "⊞ Modell-Manager öffnen")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        ctx["app"].processEvents()

        assert _FakeModelManagerDialog.calls == [
            ("init", dlg, "http://myhost:11434"),
            ("exec",),
        ]
    finally:
        _teardown(dlg, ctx["app"])


def test_55_btn_storage_browser_opens_dialog(monkeypatch) -> None:
    """Control #55: 'Storage-Browser' -> StorageBrowserDialog(parent).exec()."""
    dlg, ctx = _make_dialog(monkeypatch)
    try:
        _FakeStorageBrowserDialog.calls = []
        monkeypatch.setattr(
            "ui.dialogs.storage_browser_dialog.StorageBrowserDialog",
            _FakeStorageBrowserDialog,
        )
        button = _single_button(dlg, "Storage-Browser")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        ctx["app"].processEvents()

        assert _FakeStorageBrowserDialog.calls == [("init", dlg), ("exec",)]
    finally:
        _teardown(dlg, ctx["app"])


def test_56_chk_audio_v2_click_persists_on_ok(monkeypatch) -> None:
    """Control #56: Checkbox-Klick -> OK schreibt audio.v2_default=False."""
    dlg, ctx = _make_dialog(monkeypatch)
    try:
        _goto_tab(dlg, 1, ctx["app"])
        chk = _single_checkbox(dlg, "Audio-Analyse V2 als Standard")
        assert chk.isChecked() is True

        QTest.mouseClick(chk, Qt.MouseButton.LeftButton)
        ctx["app"].processEvents()
        assert chk.isChecked() is False

        dlg._chk_enabled.setChecked(False)
        QTest.mouseClick(dlg._btn_ok, Qt.MouseButton.LeftButton)
        ctx["app"].processEvents()

        assert (("audio", "v2_default"), False) in ctx["store"].nested_writes
        assert len(ctx["saved"]) == 1 and ctx["saved"][0][0] is False
        assert ctx["sm"].save_calls == 1
        assert dlg.result() == QDialog.DialogCode.Accepted
    finally:
        _teardown(dlg, ctx["app"])
