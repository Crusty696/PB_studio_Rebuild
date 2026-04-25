"""FR-S2-3 / Task-S2-3: BPM Half-Double-Adaptation.

Build-Up Section → spacing × 2 (halbiertes BPM-Feeling).
Drop Section → spacing × 0.5 (verdoppeltes BPM-Feeling).
Andere Sections → spacing × 1.0.
"""
from services.pacing.cut_density_modulator import (
    apply_bpm_adaptation,
    section_spacing_multiplier,
)


def test_buildup_doubles_spacing():
    assert section_spacing_multiplier("buildup") == 2.0
    assert section_spacing_multiplier("build_up") == 2.0
    assert section_spacing_multiplier("BUILDUP") == 2.0


def test_drop_halves_spacing():
    assert section_spacing_multiplier("drop") == 0.5


def test_neutral_for_other_sections():
    for s in ["chorus", "verse", "intro", "outro", "breakdown", "bridge", "transition", None, ""]:
        assert section_spacing_multiplier(s) == 1.0


class _Section:
    def __init__(self, start, end, type_):
        self.start = start
        self.end = end
        self.section_type = type_


def test_apply_bpm_adaptation_thins_in_buildup():
    sections = [_Section(0.0, 4.0, "buildup")]
    cuts = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]
    result = apply_bpm_adaptation(cuts, sections)
    # spacing × 2 → jeder zweite cut entfernt
    assert len(result) <= len(cuts) // 2 + 1


def test_apply_bpm_adaptation_keeps_drop_dense():
    sections = [_Section(0.0, 4.0, "drop")]
    cuts = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]
    # spacing × 0.5 → mehr Cuts (Interpolation)
    result = apply_bpm_adaptation(cuts, sections)
    assert len(result) >= len(cuts)


def test_apply_bpm_adaptation_neutral_section_unchanged():
    sections = [_Section(0.0, 4.0, "chorus")]
    cuts = [0.5, 1.0, 1.5, 2.0]
    result = apply_bpm_adaptation(cuts, sections)
    assert result == sorted(set(cuts))


def test_apply_bpm_adaptation_no_sections_unchanged():
    cuts = [0.5, 1.0, 1.5]
    result = apply_bpm_adaptation(cuts, sections=[])
    assert result == [0.5, 1.0, 1.5]
