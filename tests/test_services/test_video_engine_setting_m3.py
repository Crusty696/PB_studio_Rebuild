"""NEUBAU-VOLLINTEGRATION M3 (D-065 / USE-003): Video-Engine als Setting.

engine_enabled() liest jetzt das persistente Setting
video.use_pipeline_engine; die Env-Var PB_ENABLE_VIDEO_PIPELINE_ENGINE
bleibt Override. Default AUS bis Paritaet bewiesen.
"""


class _Store:
    def __init__(self, value=False):
        self.value = value

    def get_nested(self, *path, default=None):
        if path == ("video", "use_pipeline_engine"):
            return self.value
        return default


def test_setting_on_activates(monkeypatch):
    import services.settings_store as ss
    from services.video_pipeline import app_integration as ai
    monkeypatch.delenv(ai.FEATURE_FLAG, raising=False)
    monkeypatch.setattr(ss, "get_settings_store", lambda: _Store(True))
    assert ai.engine_enabled() is True


def test_default_off(monkeypatch):
    import services.settings_store as ss
    from services.video_pipeline import app_integration as ai
    monkeypatch.delenv(ai.FEATURE_FLAG, raising=False)
    monkeypatch.setattr(ss, "get_settings_store", lambda: _Store(False))
    assert ai.engine_enabled() is False


def test_env_overrides_on(monkeypatch):
    import services.settings_store as ss
    from services.video_pipeline import app_integration as ai
    monkeypatch.setenv(ai.FEATURE_FLAG, "1")
    monkeypatch.setattr(ss, "get_settings_store", lambda: _Store(False))
    assert ai.engine_enabled() is True


def test_env_overrides_off(monkeypatch):
    import services.settings_store as ss
    from services.video_pipeline import app_integration as ai
    monkeypatch.setenv(ai.FEATURE_FLAG, "0")
    monkeypatch.setattr(ss, "get_settings_store", lambda: _Store(True))
    assert ai.engine_enabled() is False


def test_store_error_falls_back_off(monkeypatch):
    import services.settings_store as ss
    from services.video_pipeline import app_integration as ai
    monkeypatch.delenv(ai.FEATURE_FLAG, raising=False)

    def boom():
        raise RuntimeError("store kaputt")

    monkeypatch.setattr(ss, "get_settings_store", boom)
    assert ai.engine_enabled() is False
