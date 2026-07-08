"""NEUBAU-VOLLINTEGRATION T2.5.3 (FR-S1-2): Vocal-on-Hold verdrahtet.

vocal_hold_spacing_modifier + dominant_stem laufen jetzt im Auto-Edit:
vocal-dominante Sections verdoppeln die Mindest-Segmentdauer.
"""
from types import SimpleNamespace

from services.pacing.stem_section_aggregator import dominant_stem
from services.pacing.vocal_hold_modifier import vocal_hold_spacing_modifier
from services.pacing_edit_helpers import _enforce_minimum_durations


def _sec(start, end, stype="VERSE"):
    return SimpleNamespace(start=start, end=end, section_type=stype)


class TestVocalHoldWindow:
    def test_window_doubles_min_duration(self):
        """VERSE-Minimum 4s -> im Hold-Fenster 8s: 4s-Cuts fliegen raus."""
        sections = [_sec(0, 100, "VERSE")]
        cuts = [0.0, 4.0, 8.0, 12.0, 16.0, 100.0]
        base = _enforce_minimum_durations(cuts, sections, 100.0)
        assert 4.0 in base and 8.0 in base  # ohne Hold bleiben 4s-Abstaende

        held = _enforce_minimum_durations(
            cuts, sections, 100.0,
            min_multiplier_windows=[(0.0, 100.0, 2.0)],
        )
        assert 4.0 not in held          # 4s < 8s-Minimum
        assert 8.0 in held and 16.0 in held  # 8s-Abstaende bleiben

    def test_window_only_applies_inside(self):
        sections = [_sec(0, 100, "VERSE")]
        cuts = [0.0, 4.0, 8.0, 54.0, 58.0, 100.0]
        held = _enforce_minimum_durations(
            cuts, sections, 100.0,
            min_multiplier_windows=[(50.0, 100.0, 2.0)],
        )
        assert 4.0 in held and 8.0 in held  # vor dem Fenster unveraendert
        assert 58.0 not in held             # im Fenster: 4s < 8s

    def test_none_windows_is_noop(self):
        sections = [_sec(0, 100, "VERSE")]
        cuts = [0.0, 4.0, 8.0, 100.0]
        assert _enforce_minimum_durations(cuts, sections, 100.0) == \
               _enforce_minimum_durations(cuts, sections, 100.0,
                                          min_multiplier_windows=None)


class TestModifierAndDominant:
    def test_modifier_threshold(self):
        assert vocal_hold_spacing_modifier(
            {"vocals": 0.45, "drums": 0.3, "bass": 0.15, "other": 0.1}) == 2.0
        assert vocal_hold_spacing_modifier(
            {"vocals": 0.10, "drums": 0.5, "bass": 0.2, "other": 0.2}) == 1.0

    def test_dominant_stem_from_normalized_means(self):
        """Adapter-Vertrag: L1-normalisierte per-Beat-Mittel wie im Service."""
        means = {"drums": 0.5, "bass": 0.2, "vocals": 0.2, "other": 0.1}
        assert dominant_stem(means) == "drums"
        assert dominant_stem({"drums": 0.3, "bass": 0.3,
                              "vocals": 0.2, "other": 0.2}) is None
