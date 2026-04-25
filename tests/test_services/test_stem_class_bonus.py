"""FR-S2-2 / Task-S2-2: Stem-Class-Bonus.

Wenn die dominante Stem einer Section mit dem Shot-Type des Kandidaten
übereinstimmt → Bonus +0.15.
"""
import pytest

from services.pacing.stem_class_bonus import compute_stem_class_bonus


def test_bonus_when_dominant_stem_matches_top_class():
    shot_conf = {"vocal_dominant": 0.55, "drum_dominant": 0.20, "melody_dominant": 0.15, "bass_dominant": 0.10}
    bonus = compute_stem_class_bonus("vocals", shot_conf, bonus_amount=0.15, min_confidence=0.30)
    assert bonus == 0.15


def test_no_bonus_when_dominant_stem_mismatch():
    shot_conf = {"vocal_dominant": 0.55, "drum_dominant": 0.20, "melody_dominant": 0.15, "bass_dominant": 0.10}
    bonus = compute_stem_class_bonus("drums", shot_conf, bonus_amount=0.15, min_confidence=0.30)
    assert bonus == 0.0


def test_no_bonus_when_top_below_confidence_threshold():
    shot_conf = {"vocal_dominant": 0.28, "drum_dominant": 0.27, "melody_dominant": 0.25, "bass_dominant": 0.20}
    bonus = compute_stem_class_bonus("vocals", shot_conf, bonus_amount=0.15, min_confidence=0.30)
    assert bonus == 0.0


def test_no_bonus_when_dominant_stem_is_none():
    shot_conf = {"vocal_dominant": 0.55, "drum_dominant": 0.20, "melody_dominant": 0.15, "bass_dominant": 0.10}
    bonus = compute_stem_class_bonus(None, shot_conf, bonus_amount=0.15, min_confidence=0.30)
    assert bonus == 0.0


def test_other_stem_never_bonuses():
    """'other' ist Sammeltopf — kein eindeutiger Match möglich."""
    shot_conf = {"vocal_dominant": 0.40, "drum_dominant": 0.20, "melody_dominant": 0.30, "bass_dominant": 0.10}
    bonus = compute_stem_class_bonus("other", shot_conf, bonus_amount=0.15, min_confidence=0.30)
    assert bonus == 0.0


def test_unknown_stem_raises():
    shot_conf = {"vocal_dominant": 0.55, "drum_dominant": 0.20, "melody_dominant": 0.15, "bass_dominant": 0.10}
    with pytest.raises(ValueError):
        compute_stem_class_bonus("synth_pad", shot_conf, bonus_amount=0.15, min_confidence=0.30)


def test_bonus_drums_to_drum_dominant():
    shot_conf = {"vocal_dominant": 0.10, "drum_dominant": 0.60, "melody_dominant": 0.20, "bass_dominant": 0.10}
    bonus = compute_stem_class_bonus("drums", shot_conf, bonus_amount=0.15, min_confidence=0.30)
    assert bonus == 0.15


def test_bonus_bass_to_bass_dominant():
    shot_conf = {"vocal_dominant": 0.10, "drum_dominant": 0.20, "melody_dominant": 0.20, "bass_dominant": 0.50}
    bonus = compute_stem_class_bonus("bass", shot_conf, bonus_amount=0.15, min_confidence=0.30)
    assert bonus == 0.15
