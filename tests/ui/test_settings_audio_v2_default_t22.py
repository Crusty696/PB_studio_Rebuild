"""NEUBAU-VOLLINTEGRATION T2.2 (USE-012): audio.v2_default im Settings-Dialog.

Vorher: get_nested("audio","v2_default") wurde gelesen
(ui/controllers/audio_analysis.py), aber es gab im ganzen Repo keinen
set_nested-Schreiber und kein UI — das Setting war unerreichbar.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


class _FakeStore:
    def __init__(self, initial=None):
        self.data = dict(initial or {})
        self.set_calls = []

    def get_nested(self, *path, default=None):
        cur = self.data
        for p in path:
            if not isinstance(cur, dict) or p not in cur:
                return default
            cur = cur[p]
        return cur


    # ShortcutManager-Kompatibilitaet (Singleton kann je nach Test-Reihenfolge
    # mit diesem Store initialisiert werden)
    def get_shortcut(self, action_id, default=""):
        return default

    def set_all_shortcuts(self, shortcuts):
        self.data["shortcuts"] = dict(shortcuts)

    def set_nested(self, *path, value=None):
        self.set_calls.append((path, value))
        cur = self.data
        for p in path[:-1]:
            cur = cur.setdefault(p, {})
        cur[path[-1]] = value

    # vom Dialog-Lade-/Speicherpfad mitverwendet
    def save_ollama_settings(self, enabled, url, model):
        self.data["ollama"] = {"enabled": enabled, "url": url, "model": model}


def _make_dialog(monkeypatch, store):
    import ui.dialogs.settings_dialog as sd
    monkeypatch.setattr(sd, "get_settings_store", lambda: store)
    monkeypatch.setattr(sd, "get_ollama_settings", lambda: {
        "enabled": False, "url": "http://localhost:11434", "model": "",
    })
    return sd.SettingsDialog()


def test_checkbox_reflects_stored_value(monkeypatch, qapp=None):
    _qapp()
    store = _FakeStore({"audio": {"v2_default": False}})
    dlg = _make_dialog(monkeypatch, store)
    assert dlg._chk_audio_v2_default.isChecked() is False


def test_checkbox_default_true_when_unset(monkeypatch):
    _qapp()
    dlg = _make_dialog(monkeypatch, _FakeStore())
    assert dlg._chk_audio_v2_default.isChecked() is True


def test_accept_persists_v2_default(monkeypatch):
    """Kern-Verify: OK schreibt set_nested('audio','v2_default', ...)."""
    _qapp()
    store = _FakeStore()
    dlg = _make_dialog(monkeypatch, store)
    dlg._chk_audio_v2_default.setChecked(False)
    dlg._shortcut_tab.apply = lambda: None  # Shortcut-Persistenz nicht Testziel
    dlg._on_accept()
    assert (("audio", "v2_default"), False) in store.set_calls
    assert store.get_nested("audio", "v2_default", default=True) is False


def test_reader_uses_persisted_value(monkeypatch):
    """Roundtrip zum echten Leser: audio_analysis-Routing sieht das Setting."""
    _qapp()
    store = _FakeStore({"audio": {"v2_default": False}})
    import services.settings_store as ss
    monkeypatch.setattr(ss, "get_settings_store", lambda: store)
    assert ss.get_settings_store().get_nested(
        "audio", "v2_default", default=True) is False
