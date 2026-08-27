"""B-912: Cut-Rate bleibt nach Drop-/Onset-Eingriffen verbindlich."""

from types import SimpleNamespace

from services.pacing_edit_helpers import (
    _enforce_cut_rate_floor,
    _enforce_max_segment_duration,
)


BEATS = [i * 0.5 for i in range(41)]  # 120 BPM, 20 Sekunden


def _durations(cuts):
    return [b - a for a, b in zip(cuts, cuts[1:])]


def _section(start, end, section_type="DROP"):
    return SimpleNamespace(start=start, end=end, section_type=section_type)


def test_vier_beats_entfernen_spaete_mini_schnitte():
    dense = [0.0, 0.48, 1.02, 1.55, 2.01, 3.0, 4.0, 6.0, 8.0]

    result = _enforce_cut_rate_floor(
        dense, BEATS, [], None, 8.0, base_step=4)

    assert min(_durations(result)) >= 2.0 - 1e-9
    assert result[0] == 0.0
    assert result[-1] == 8.0


def test_nahe_section_pflichtpunkte_bleiben_trotz_ruhe_floor():
    cuts = [0.0, 2.0, 4.03, 5.04, 6.0, 8.0, 10.0]
    sections = [
        _section(0.0, 4.0, "BUILDUP"),
        _section(4.0, 5.0, "DROP"),
        _section(5.0, 10.0, "CHORUS"),
    ]

    result = _enforce_cut_rate_floor(
        cuts, BEATS, [], sections, 10.0, base_step=4)

    assert 4.03 in result
    assert 5.04 in result
    assert 5.04 - 4.03 < 2.0


def test_ein_beat_erlaubt_schnelle_drop_schnitte():
    dense = [i * 0.5 for i in range(9)]
    sections = [_section(0.0, 4.0)]

    result = _enforce_cut_rate_floor(
        dense, BEATS, [], sections, 4.0, base_step=1)

    assert _durations(result) == [0.5] * 8


def test_source_limit_wird_nach_ausduennung_neu_gesetzt():
    result = _enforce_max_segment_duration([0.0, 12.0], BEATS, 5.0)

    assert max(_durations(result)) <= 5.0
    assert result[0] == 0.0
    assert result[-1] == 12.0
