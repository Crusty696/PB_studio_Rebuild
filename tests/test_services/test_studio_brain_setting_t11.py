"""NEUBAU-VOLLINTEGRATION T1.1 (USE-001): Studio-Brain als persistentes Setting.

Vorher: Aktivierung ausschliesslich ueber Env-Var
PB_USE_STUDIO_BRAIN_PIPELINE, die niemand setzte — Pipeline, Reranker,
DecisionRecorder blieben toter Code.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _Store:
    def __init__(self, value=False):
        self.value = value
        self.set_calls = []

    def get_nested(self, *path, default=None):
        if path == ("pacing", "use_studio_brain"):
            return self.value
        return default

    def set_nested(self, *path, value=None):
        self.set_calls.append((path, value))
        if path == ("pacing", "use_studio_brain"):
            self.value = value


class TestBridgeGate:
    def test_setting_activates_pipeline(self, monkeypatch):
        import services.settings_store as ss
        from services.pacing import bridge
        monkeypatch.delenv(bridge.ENV_VAR, raising=False)
        monkeypatch.setattr(ss, "get_settings_store", lambda: _Store(True))
        assert bridge.use_studio_brain_pipeline() is True

    def test_default_off(self, monkeypatch):
        import services.settings_store as ss
        from services.pacing import bridge
        monkeypatch.delenv(bridge.ENV_VAR, raising=False)
        monkeypatch.setattr(ss, "get_settings_store", lambda: _Store(False))
        assert bridge.use_studio_brain_pipeline() is False

    def test_env_var_overrides_setting_on(self, monkeypatch):
        import services.settings_store as ss
        from services.pacing import bridge
        monkeypatch.setenv(bridge.ENV_VAR, "1")
        monkeypatch.setattr(ss, "get_settings_store", lambda: _Store(False))
        assert bridge.use_studio_brain_pipeline() is True

    def test_env_var_overrides_setting_off(self, monkeypatch):
        """Nicht-truthy Env-Wert erzwingt AUS (Test-Determinismus)."""
        import services.settings_store as ss
        from services.pacing import bridge
        monkeypatch.setenv(bridge.ENV_VAR, "0")
        monkeypatch.setattr(ss, "get_settings_store", lambda: _Store(True))
        assert bridge.use_studio_brain_pipeline() is False

    def test_store_error_falls_back_to_off(self, monkeypatch):
        import services.settings_store as ss
        from services.pacing import bridge
        monkeypatch.delenv(bridge.ENV_VAR, raising=False)

        def boom():
            raise RuntimeError("store kaputt")

        monkeypatch.setattr(ss, "get_settings_store", boom)
        assert bridge.use_studio_brain_pipeline() is False


class TestPanelCheckbox:
    def test_checkbox_loads_and_persists(self, monkeypatch):
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        import services.settings_store as ss
        store = _Store(True)
        monkeypatch.setattr(ss, "get_settings_store", lambda: store)
        monkeypatch.setattr(ss, "get_ollama_settings",
                            lambda: {"enabled": True})
        from ui.workspaces.schnitt.tab_pacing_anker import SchnittTabPacingAnker
        tab = SchnittTabPacingAnker()
        assert tab.chk_studio_brain.isChecked() is True
        tab.chk_studio_brain.setChecked(False)
        assert (("pacing", "use_studio_brain"), False) in store.set_calls
