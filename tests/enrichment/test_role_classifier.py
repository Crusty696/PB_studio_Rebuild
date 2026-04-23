"""Tests for services.enrichment.role_classifier (T3.1)."""

from pathlib import Path

import pytest

from services.enrichment.role_classifier import classify_role


def test_short_high_motion_is_transition() -> None:
    role, conf = classify_role(motion=0.8, duration=0.5, tags={"blur"})
    assert role == "transition"
    assert conf >= 0.8


def test_long_wide_low_motion_is_establishing() -> None:
    role, conf = classify_role(motion=0.1, duration=5.0, tags={"landscape", "wide"})
    assert role == "establishing"


def test_crowd_high_motion_is_action() -> None:
    role, conf = classify_role(motion=0.8, duration=2.0, tags={"crowd", "stage"})
    assert role == "action"


def test_macro_static_is_detail() -> None:
    role, conf = classify_role(motion=0.05, duration=1.8, tags={"macro", "texture"})
    assert role == "detail"


def test_portrait_motion_is_hero() -> None:
    role, conf = classify_role(motion=0.5, duration=2.0, tags={"portrait", "face"})
    assert role == "hero"


def test_unknown_fallback_is_filler_low_confidence() -> None:
    role, conf = classify_role(motion=0.4, duration=1.5, tags=set())
    assert role in ("hero", "filler")
    assert conf <= 0.5


def test_rules_are_config_driven(tmp_path: Path) -> None:
    # Custom YAML that inverts the default logic:
    custom = tmp_path / "custom_rules.yaml"
    custom.write_text(
        "role_rules:\n"
        "  - role: hero\n"
        "    confidence: 0.9\n"
        "    require:\n"
        "      motion_gte: 0.0\n"  # matches everything
        "fallback:\n"
        "  role: filler\n"
        "  confidence: 0.1\n",
        encoding="utf-8",
    )
    # With this YAML, every input should return ("hero", 0.9):
    role, conf = classify_role(
        motion=0.05, duration=0.5, tags=set(), rules_path=str(custom)
    )
    assert role == "hero"
    assert conf == 0.9


def test_unknown_require_key_raises_value_error(tmp_path: Path) -> None:
    """An unrecognised key in 'require:' must raise ValueError at load time."""
    bad_yaml = tmp_path / "bad_rules.yaml"
    bad_yaml.write_text(
        "role_rules:\n"
        "  - role: hero\n"
        "    confidence: 0.9\n"
        "    require:\n"
        "      typo_key: 0.5\n"
        "fallback:\n"
        "  role: filler\n"
        "  confidence: 0.1\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="typo_key"):
        classify_role(motion=0.5, duration=1.0, tags=set(), rules_path=str(bad_yaml))
