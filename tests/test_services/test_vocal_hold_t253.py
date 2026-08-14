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
        """Im Hold-Fenster gilt das doppelte VERSE-Minimum.

        B-835: Die Aussage ist unveraendert, nur die Skala. Das VERSE-Minimum
        liegt seit dem Absenken bei 1,31s statt 4,0s, das Hold-Fenster
        verdoppelt es auf 2,62s. Der Test rechnet deshalb mit Abstaenden
        diesseits und jenseits dieser Grenze statt mit den alten 4s/8s.

        Nebenwirkung, die dieser Test festhaelt: Vocal-on-Hold wirkt in
        absoluten Sekunden schwaecher als vorher. Der Mechanismus — Faktor 2
        auf das jeweilige Section-Minimum — ist derselbe geblieben.
        """
        from services.pacing_beat_grid import SECTION_MIN_DURATION

        verse_min = SECTION_MIN_DURATION["VERSE"]
        eng = round(verse_min * 1.5, 2)    # ueber dem Minimum, unter dem Doppelten
        weit = round(verse_min * 2.5, 2)   # ueber dem Doppelten

        sections = [_sec(0, 100, "VERSE")]
        cuts = [0.0, eng, eng * 2, weit + eng * 2, 100.0]
        base = _enforce_minimum_durations(cuts, sections, 100.0)
        assert eng in base, "ohne Hold reicht der einfache Mindestabstand"

        held = _enforce_minimum_durations(
            cuts, sections, 100.0,
            min_multiplier_windows=[(0.0, 100.0, 2.0)],
        )
        assert eng not in held, (
            f"{eng}s unterschreitet das verdoppelte Minimum "
            f"({verse_min * 2:.2f}s) und muss entfallen"
        )
        assert eng * 2 in held, "der doppelte Abstand muss bestehen bleiben"

    def test_window_only_applies_inside(self):
        """B-835: gleiche Aussage, an der neuen Skala gerechnet.

        Der Abstand ``eng`` liegt ueber dem VERSE-Minimum, aber unter dem
        verdoppelten. Vor dem Fenster muss er deshalb bestehen bleiben, im
        Fenster entfallen.
        """
        from services.pacing_beat_grid import SECTION_MIN_DURATION

        eng = round(SECTION_MIN_DURATION["VERSE"] * 1.5, 2)
        sections = [_sec(0, 100, "VERSE")]
        cuts = [0.0, eng, eng * 2, 54.0, 54.0 + eng, 100.0]
        held = _enforce_minimum_durations(
            cuts, sections, 100.0,
            min_multiplier_windows=[(50.0, 100.0, 2.0)],
        )
        assert eng in held, "vor dem Fenster gilt das einfache Minimum"
        assert 54.0 + eng not in held, "im Fenster gilt das doppelte Minimum"

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
