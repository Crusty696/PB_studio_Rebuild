"""R-S0-2 Bridge-Tests: Feature-Flag PB_USE_STUDIO_BRAIN_PIPELINE.

Foundation Slice 0 schützt die Legacy-Pipeline gegen versehentliche
Aktivierung halb-fertiger Studio-Brain-Pfade. Default (Flag nicht gesetzt
oder = "0") muss bit-identisch zu vor-Bridge-Verhalten sein.
"""
from __future__ import annotations

import logging

import pytest

from services.pacing.bridge import (
    ENV_VAR,
    maybe_use_studio_brain_pipeline,
    use_studio_brain_pipeline,
)
@pytest.fixture(autouse=True)
def _stub_settings_store(monkeypatch):
    import services.settings_store as ss
    from tests.test_services.test_studio_brain_setting_t11 import _Store
    monkeypatch.setattr(ss, "get_settings_store", lambda: _Store(False))

def test_flag_default_off(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert use_studio_brain_pipeline() is False


def test_flag_explicit_off(monkeypatch):
    for v in ("0", "false", "FALSE", "no", "off", ""):
        monkeypatch.setenv(ENV_VAR, v)
        assert use_studio_brain_pipeline() is False, f"value {v!r} should be off"


def test_flag_on_variants(monkeypatch):
    for v in ("1", "true", "TRUE", "yes", "on", "On"):
        monkeypatch.setenv(ENV_VAR, v)
        assert use_studio_brain_pipeline() is True, f"value {v!r} should be on"


def test_maybe_use_returns_false_when_flag_off(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert maybe_use_studio_brain_pipeline(audio_id=1, video_clip_ids=[1, 2]) is False


def test_maybe_use_returns_true_with_info_when_flag_on(monkeypatch, caplog):
    """Flag=True aktiviert den Studio-Brain-Pacing-Pfad."""
    monkeypatch.setenv(ENV_VAR, "1")
    with caplog.at_level(logging.INFO, logger="services.pacing.bridge"):
        result = maybe_use_studio_brain_pipeline(audio_id=42, video_clip_ids=[7, 8, 9])
    assert result is True
    assert any(
        "PB_USE_STUDIO_BRAIN_PIPELINE" in rec.message
        and "Studio-Brain-Pacing aktiv" in rec.message
        for rec in caplog.records
    )


def test_bridge_flag_does_not_claim_unimplemented_when_pipeline_is_enabled(monkeypatch, caplog):
    from services.pacing import bridge

    monkeypatch.setenv(bridge.ENV_VAR, "1")

    assert bridge.use_studio_brain_pipeline() is True
    assert bridge.maybe_use_studio_brain_pipeline(audio_id=1, video_clip_ids=[1, 2]) is True
    assert "Bridge noch nicht implementiert" not in caplog.text


def test_auto_edit_phase3_legacy_path_unchanged_when_flag_off(monkeypatch):
    """Snapshot-Sicherheitsnetz: ohne Flag wird Bridge-Stub nie ausgeführt."""
    from services.pacing import bridge

    monkeypatch.delenv(ENV_VAR, raising=False)
    calls: list[tuple] = []

    real = bridge.maybe_use_studio_brain_pipeline

    def _spy(**kwargs):
        calls.append(("called", tuple(kwargs.items())))
        return real(**kwargs)

    monkeypatch.setattr(bridge, "maybe_use_studio_brain_pipeline", _spy)
    assert bridge.maybe_use_studio_brain_pipeline(audio_id=1, video_clip_ids=[]) is False
    assert calls == [("called", (("audio_id", 1), ("video_clip_ids", [])))]
