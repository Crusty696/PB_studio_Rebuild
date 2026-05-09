import pytest
from services.pacing_profile import PacingProfile


def test_default_construction():
    p = PacingProfile()
    assert p.audio_id is None
    assert p.video_id is None
    assert p.cut_rate_index == 2
    assert p.style_preset == "Standard"
    assert p.energy_reactivity == 50
    assert p.breakdown == "halve"
    assert p.manual_density_curve is None
    assert p.anchors == []


def test_from_preset_techno():
    p = PacingProfile.from_preset("Techno")
    assert p.cut_rate_index == 2  # 4 Beats
    assert p.energy_reactivity == 70
    assert p.breakdown == "halve"
    assert p.style_preset == "Techno"


def test_from_preset_cinematic():
    p = PacingProfile.from_preset("Cinematic")
    assert p.cut_rate_index == 4  # 16 Beats
    assert p.energy_reactivity == 30
    assert p.breakdown == "none"


def test_from_preset_unknown_raises():
    with pytest.raises(ValueError):
        PacingProfile.from_preset("DoesNotExist")


def test_to_advanced_settings_maps_correctly():
    p = PacingProfile(audio_id=1, video_id=2, vibe="dunkel",
                      cut_rate_index=3, style_preset="House",
                      energy_reactivity=60, breakdown="force16")
    s = p.to_advanced_settings()
    assert s.base_cut_rate == 8
    assert s.energy_reactivity == 60
    assert s.breakdown_behavior == "force16"
    assert s.vibe == "dunkel"
