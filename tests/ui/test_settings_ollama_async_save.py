"""Freeze-Fix: Settings-Speichern prueft das Ollama-Modell ASYNC.

Vorher rief _on_accept -> _validate_ollama_model -> client.list_models()
SYNCHRON im UI-Thread (bis 5s, bei DNS-Pleite laenger) -> Speichern-Button
fror die App ein. Jetzt via _OllamaTestWorker im QThread; die Entscheidung
faellt in _on_validate_finished.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class _Store:
    def get_nested(self, *path, default=None):
        return default

    def set_nested(self, *path, value=None):
        pass

    # Je nach Import-Reihenfolge kann die echte get_ollama_settings() den
    # Store direkt fragen — Fake vollstaendig halten (Test-Isolation).
    def get_ollama_settings(self):
        return {"enabled": True, "url": "http://localhost:11434", "model": "gemma:2b"}

    # ShortcutEditorTab greift beim Dialog-Bau darauf zu.
    def get_shortcut(self, action_name, default=None):
        return default

    def get_all_shortcuts(self):
        return {}

    def set_all_shortcuts(self, mapping):
        pass


def _make_dialog(monkeypatch):
    _app()
    import services.settings_store as ss
    monkeypatch.setattr(ss, "get_settings_store", lambda: _Store())
    monkeypatch.setattr(
        ss, "get_ollama_settings",
        lambda: {"enabled": True, "url": "http://localhost:11434", "model": "gemma:2b"},
    )
    import ui.dialogs.settings_dialog as sd
    monkeypatch.setattr(sd, "save_ollama_settings", lambda **k: None)
    dlg = sd.SettingsDialog()
    return dlg


class TestValidateDecision:
    def test_offline_saves_anyway(self, monkeypatch):
        """Ollama unerreichbar (ok=False) -> trotzdem speichern (offline-tolerant)."""
        dlg = _make_dialog(monkeypatch)
        committed = {}
        monkeypatch.setattr(dlg, "_commit_and_accept",
                            lambda e, u, m: committed.update(done=(e, u, m)))
        dlg._pending_save = (True, "http://x", "gemma:2b")
        dlg._on_validate_finished(False, "nicht erreichbar", [])
        assert committed["done"] == (True, "http://x", "gemma:2b")

    def test_model_installed_saves(self, monkeypatch):
        dlg = _make_dialog(monkeypatch)
        committed = {}
        monkeypatch.setattr(dlg, "_commit_and_accept",
                            lambda e, u, m: committed.update(done=True))
        dlg._pending_save = (True, "http://x", "gemma:2b")
        dlg._on_validate_finished(True, "ok", ["gemma:2b", "llama3"])
        assert committed.get("done") is True

    def test_empty_list_saves(self, monkeypatch):
        dlg = _make_dialog(monkeypatch)
        committed = {}
        monkeypatch.setattr(dlg, "_commit_and_accept",
                            lambda e, u, m: committed.update(done=True))
        dlg._pending_save = (True, "http://x", "gemma:2b")
        dlg._on_validate_finished(True, "ok", [])
        assert committed.get("done") is True

    def test_missing_model_asks_and_cancel_does_not_save(self, monkeypatch):
        dlg = _make_dialog(monkeypatch)
        committed = {}
        monkeypatch.setattr(dlg, "_commit_and_accept",
                            lambda e, u, m: committed.update(done=True))
        # QMessageBox.exec -> Cancel
        from PySide6.QtWidgets import QMessageBox
        monkeypatch.setattr(QMessageBox, "exec",
                            lambda self: QMessageBox.StandardButton.Cancel)
        dlg._pending_save = (True, "http://x", "gemma:2b")
        dlg._on_validate_finished(True, "ok", ["llama3", "phi3"])
        assert "done" not in committed  # nicht gespeichert
        assert dlg._btn_ok.isEnabled()  # OK wieder aktiv

    def test_missing_model_save_choice_saves(self, monkeypatch):
        dlg = _make_dialog(monkeypatch)
        committed = {}
        monkeypatch.setattr(dlg, "_commit_and_accept",
                            lambda e, u, m: committed.update(done=True))
        from PySide6.QtWidgets import QMessageBox
        monkeypatch.setattr(QMessageBox, "exec",
                            lambda self: QMessageBox.StandardButton.Save)
        dlg._pending_save = (True, "http://x", "gemma:2b")
        dlg._on_validate_finished(True, "ok", ["llama3"])
        assert committed.get("done") is True


def test_on_accept_is_async_no_sync_list_models(monkeypatch):
    """Quelltext-Vertrag: _on_accept nutzt den Worker/QThread, ruft NICHT
    mehr synchron _validate_ollama_model/list_models im UI-Thread."""
    import inspect

    import ui.dialogs.settings_dialog as sd
    src = inspect.getsource(sd.SettingsDialog._on_accept)
    assert "_OllamaTestWorker" in src
    assert "QThread" in src
    assert "_validate_ollama_model" not in src
    # die alte synchrone Methode existiert nicht mehr
    assert not hasattr(sd.SettingsDialog, "_validate_ollama_model")
