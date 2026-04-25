"""FR-S1-2 / Task-S1-2: Vocal-on-Hold spacing modifier.

Wenn die Vocal-Energy einer Section einen Threshold übersteigt, soll die
Cut-Rate halbiert werden (spacing × 2). Das verhindert hyperaktive Schnitte
über Lyric-Phrasen.
"""
from services.pacing.vocal_hold_modifier import vocal_hold_spacing_modifier


def test_vocal_hold_doubles_spacing_when_vocal_dominant():
    stem_energies = {"vocals": 0.55, "drums": 0.20, "bass": 0.15, "other": 0.10}
    mod = vocal_hold_spacing_modifier(stem_energies, threshold=0.40)
    assert mod == 2.0


def test_no_modifier_below_threshold():
    stem_energies = {"vocals": 0.30, "drums": 0.40, "bass": 0.20, "other": 0.10}
    mod = vocal_hold_spacing_modifier(stem_energies, threshold=0.40)
    assert mod == 1.0


def test_handles_missing_vocals_key():
    stem_energies = {"drums": 0.50, "bass": 0.30, "other": 0.20}
    mod = vocal_hold_spacing_modifier(stem_energies, threshold=0.40)
    assert mod == 1.0


def test_empty_energies():
    assert vocal_hold_spacing_modifier({}, threshold=0.40) == 1.0


def test_threshold_inclusive():
    stem_energies = {"vocals": 0.40, "drums": 0.30, "bass": 0.20, "other": 0.10}
    mod = vocal_hold_spacing_modifier(stem_energies, threshold=0.40)
    assert mod == 2.0
