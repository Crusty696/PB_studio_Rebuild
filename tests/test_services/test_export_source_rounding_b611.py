"""B-611: Export-Crash durch hochgerundeten source_end.

Reales Szenario (Projekt outputs/21, TimelineEntry 1385): source_end wurde
beim Pacing auf 4 Dezimalen gerundet (8.666667 -> 8.6667) und lag damit
33 us ueber der echten Clip-Laenge. Die alte 1e-6-Toleranz in
_source_duration_from_entry warf ValueError und brach den GESAMTEN Export ab.
"""
from types import SimpleNamespace

import pytest

from services.export_service import _source_duration_from_entry


def _entry(source_start, source_end, eid=1385):
    return SimpleNamespace(id=eid, source_start=source_start, source_end=source_end)


def test_rounding_overshoot_is_clamped_not_raised():
    """8.6667 (gerundet) vs echte Clip-Laenge 8.666667: darf NICHT crashen,
    source_duration wird auf die Clip-Laenge geclampt."""
    e = _entry(0.0, 8.6667)
    dur = _source_duration_from_entry(e, fallback_duration=8.6667,
                                      clip_duration=8.666667)
    assert dur == pytest.approx(8.666667, abs=1e-6)
    assert dur <= 8.666667 + 1e-9


def test_exact_fit_unchanged():
    e = _entry(0.0, 5.0)
    dur = _source_duration_from_entry(e, fallback_duration=5.0, clip_duration=5.0)
    assert dur == pytest.approx(5.0)


def test_mid_clip_rounding_overshoot_clamped():
    """source_start > 0, Ende minimal ueber Clip-Ende -> auf Rest clampen."""
    e = _entry(2.0, 10.0001)
    dur = _source_duration_from_entry(e, fallback_duration=8.0, clip_duration=10.0)
    assert dur == pytest.approx(8.0, abs=1e-6)


def test_gross_overshoot_still_raises():
    """Ein GROBER Ueberschuss (>50ms) ist echte Korruption und muss weiterhin
    einen Fehler werfen (kein stilles Verschlucken)."""
    e = _entry(0.0, 12.0)
    with pytest.raises(ValueError, match="ueberschreitet clip duration"):
        _source_duration_from_entry(e, fallback_duration=12.0, clip_duration=8.0)


def test_negative_source_start_still_raises():
    e = _entry(-1.0, 5.0)
    with pytest.raises(ValueError, match="source_start"):
        _source_duration_from_entry(e, fallback_duration=6.0, clip_duration=10.0)
