"""T6.3 — Sanity tests for the pacing-config YAML layout.

The PacingScorer already has a runtime test for weights_profile="default";
this file nails down the on-disk contract: all 5 YAMLs load cleanly, and
the profile-inheritance story (defaults + overrides) works as designed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from services.pacing.scorer import DEFAULT_WEIGHTS, PacingScorer


CONFIG_ROOT = Path("config")
RULES_PATH = CONFIG_ROOT / "pacing_rules.yaml"
WEIGHTS_DIR = CONFIG_ROOT / "pacing_weights"
REQUIRED_PROFILES = ["default", "psytrance", "house", "dj_mix_auto"]


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


# ── pacing_rules.yaml ───────────────────────────────────────────────────────


def test_pacing_rules_yaml_exists_and_covers_10_sections() -> None:
    assert RULES_PATH.exists(), f"{RULES_PATH} missing"
    data = _load_yaml(RULES_PATH)
    matrix = data.get("section_role_matrix") or {}
    required_sections = {
        "intro", "warmup", "buildup", "drop", "breakdown",
        "outro", "verse", "chorus", "bridge", "transition",
    }
    assert set(matrix.keys()) >= required_sections, (
        f"Missing sections: {required_sections - set(matrix.keys())}"
    )


def test_pacing_rules_yaml_has_key_mood_gate_schema() -> None:
    data = _load_yaml(RULES_PATH)
    gate = data.get("key_mood_gate")
    assert gate is not None, "key_mood_gate missing"
    for field in ("enabled", "condition", "forbidden_moods"):
        assert field in gate, f"key_mood_gate.{field} missing"
    assert isinstance(gate["enabled"], bool)


# ── pacing_weights/ ────────────────────────────────────────────────────────


@pytest.mark.parametrize("profile", REQUIRED_PROFILES)
def test_profile_yaml_exists_and_parses(profile: str) -> None:
    path = WEIGHTS_DIR / f"{profile}.yaml"
    assert path.exists(), f"{path} missing"
    data = _load_yaml(path)
    assert isinstance(data, dict), f"{path} must be a YAML mapping"


def test_default_yaml_defines_all_13_weights() -> None:
    data = _load_yaml(WEIGHTS_DIR / "default.yaml")
    missing = set(DEFAULT_WEIGHTS.keys()) - set(data.keys())
    assert not missing, f"default.yaml missing weights: {missing}"
    # And no unknown keys leak in
    unknown = set(data.keys()) - set(DEFAULT_WEIGHTS.keys())
    assert not unknown, f"default.yaml has unknown keys: {unknown}"


def test_default_yaml_values_match_spec() -> None:
    """Design §6.5 default weights must match the committed YAML verbatim."""
    data = _load_yaml(WEIGHTS_DIR / "default.yaml")
    for key, expected in DEFAULT_WEIGHTS.items():
        actual = float(data[key])
        assert abs(actual - expected) < 1e-9, (
            f"{key}: yaml={actual} != spec default {expected}"
        )


@pytest.mark.parametrize("profile", ["psytrance", "house", "dj_mix_auto"])
def test_genre_profile_only_overrides_known_keys(profile: str) -> None:
    """Genre profiles must not introduce unknown weight names. Unknown keys in
    the YAML (e.g. segment_profile_routing in dj_mix_auto) are still allowed —
    the scorer ignores anything outside DEFAULT_WEIGHTS — but weight-looking
    names (w_*) must be canonical."""
    data = _load_yaml(WEIGHTS_DIR / f"{profile}.yaml")
    for key in data:
        if key.startswith("w_"):
            assert key in DEFAULT_WEIGHTS, (
                f"{profile}.yaml overrides unknown weight '{key}' — "
                f"allowed keys: {sorted(DEFAULT_WEIGHTS.keys())}"
            )


def test_scorer_inherits_defaults_for_unspecified_keys() -> None:
    """A profile that overrides w_key should leave the other 12 weights at defaults."""
    scorer = PacingScorer(weights_profile="psytrance")
    # psytrance.yaml bumps w_key, w_groove, w_role.
    # Expect: other 10 match default.
    untouched = set(DEFAULT_WEIGHTS.keys()) - {"w_key", "w_groove", "w_role"}
    for key in untouched:
        assert abs(scorer._weights[key] - DEFAULT_WEIGHTS[key]) < 1e-9, (
            f"{key} should remain at default but got {scorer._weights[key]}"
        )
    # And the overridden ones really changed
    assert scorer._weights["w_key"] > DEFAULT_WEIGHTS["w_key"]
    assert scorer._weights["w_groove"] > DEFAULT_WEIGHTS["w_groove"]
    assert scorer._weights["w_role"] > DEFAULT_WEIGHTS["w_role"]


def test_dj_mix_auto_declares_segment_routing() -> None:
    data = _load_yaml(WEIGHTS_DIR / "dj_mix_auto.yaml")
    routing = data.get("segment_profile_routing")
    assert routing is not None, "dj_mix_auto.yaml missing segment_profile_routing"
    assert isinstance(routing, dict)
    # Must route the other committed profiles
    assert routing.get("psytrance") == "psytrance"
    assert routing.get("house") == "house"
