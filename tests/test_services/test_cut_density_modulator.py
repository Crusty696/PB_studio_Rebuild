"""FR-S1-3 / Task-S1-3: Drop-Burst-Mode.

Bei Drop-Frames soll im Fenster ±200ms ein Cut-Burst (3 Cuts in 800ms)
erzeugt werden, gefolgt von einem 4-Bar-Hold (kein neuer Cut).
"""
import pytest

from services.pacing.cut_density_modulator import apply_drop_burst


def test_drop_burst_inserts_three_cuts_in_window():
    bpm = 120  # 1 beat = 0.5s; 1 bar (4 beats) = 2s; 4 bars = 8s
    cuts = [10.0]  # one cut far away
    drop_times = [5.0]
    result = apply_drop_burst(cuts, drop_times, bpm=bpm)
    near_drop = sorted(t for t in result if 4.6 <= t <= 6.0)
    assert len(near_drop) >= 3
    span = max(near_drop) - min(near_drop)
    assert span <= 0.85, f"Burst span {span:.2f}s > 800ms"


def test_drop_burst_holds_for_4_bars_after():
    bpm = 120  # 4 bars = 8s
    cuts = [5.5, 6.0, 6.5, 7.0, 8.0, 9.0, 12.0]
    drop_times = [5.0]
    result = apply_drop_burst(cuts, drop_times, bpm=bpm, hold_bars=4)
    burst_end = 5.0 + 0.4  # 200ms forward window for burst
    hold_until = 5.0 + 8.0  # 4 bars at 120bpm
    in_hold_window = [t for t in result if burst_end < t < hold_until]
    assert in_hold_window == [], (
        f"Hold-Bars verletzt: cuts {in_hold_window} im Fenster ({burst_end}, {hold_until})"
    )


def test_no_drops_returns_input_sorted_unique():
    cuts = [3.0, 1.0, 1.0, 2.0]
    result = apply_drop_burst(cuts, drop_times=[], bpm=120)
    assert result == [1.0, 2.0, 3.0]


def test_multiple_drops():
    bpm = 120
    cuts = [20.0]
    drops = [3.0, 12.0]
    result = apply_drop_burst(cuts, drops, bpm=bpm)
    near_first = [t for t in result if 2.6 <= t <= 4.0]
    near_second = [t for t in result if 11.6 <= t <= 13.0]
    assert len(near_first) >= 3
    assert len(near_second) >= 3


def test_invalid_bpm_raises():
    with pytest.raises(ValueError):
        apply_drop_burst([1.0], [0.5], bpm=0)
