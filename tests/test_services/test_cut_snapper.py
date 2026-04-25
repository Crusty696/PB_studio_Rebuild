"""FR-S1-1 / Task-S1-1: Cut-Snapper — Beat-Time auf nächsten Onset snappen.

Schmaler Helper für die Pacing-Pipeline: nimmt einen Beat-Cut-Zeitpunkt
und eine Liste von Onset-Zeitpunkten und verschiebt den Cut auf den
nächsten Onset, sofern dieser innerhalb von ±max_shift_ms liegt.
"""
from __future__ import annotations

import numpy as np

from services.pacing.cut_snapper import snap_to_onset, snap_cuts


def test_snap_within_window():
    onsets = [1.0, 2.0, 3.0]
    # Cut bei 1.02s → Onset bei 1.0s (Δ=20ms) im Fenster ±50ms
    snapped = snap_to_onset(1.02, onsets, max_shift_ms=50)
    assert snapped == 1.0


def test_no_snap_outside_window():
    onsets = [1.0, 3.0]
    # Cut bei 2.0s → nächster Onset 1.0s (Δ=1000ms) → kein Snap
    snapped = snap_to_onset(2.0, onsets, max_shift_ms=50)
    assert snapped == 2.0


def test_snap_picks_nearest():
    onsets = [0.95, 1.07]
    # Cut bei 1.0s → näher zu 0.95 (Δ=50ms) als 1.07 (Δ=70ms) → 0.95 wenn ≤50ms
    snapped = snap_to_onset(1.0, onsets, max_shift_ms=50)
    assert snapped == 0.95


def test_empty_onsets_returns_input():
    assert snap_to_onset(1.5, [], max_shift_ms=50) == 1.5
    assert snap_to_onset(1.5, np.array([]), max_shift_ms=50) == 1.5


def test_negative_clamp():
    """Onset vor t=0 wird ignoriert wenn der Cut bei einem späteren Beat liegt."""
    onsets = [-0.01, 0.5]
    snapped = snap_to_onset(0.50, onsets, max_shift_ms=20)
    assert snapped == 0.5


def test_snap_cuts_batch_preserves_order_and_uniqueness():
    onsets = [1.01, 2.0, 3.0]
    cuts = [1.0, 2.5, 3.0]  # 1.0→1.01, 2.5 bleibt (Δ=500ms), 3.0 bleibt
    snapped = snap_cuts(cuts, onsets, max_shift_ms=50)
    assert snapped == [1.01, 2.5, 3.0]
    # Sortiert + dedupliziert
    assert snapped == sorted(set(snapped))


def test_snap_cuts_collisions_dedup():
    """Wenn 2 Cuts auf denselben Onset snappen, behalten wir nur einen Eintrag."""
    onsets = [1.0]
    cuts = [0.98, 1.02]  # beide snappen auf 1.0
    snapped = snap_cuts(cuts, onsets, max_shift_ms=50)
    assert snapped == [1.0]


def test_snap_cuts_deterministic():
    onsets = [1.0, 2.0, 3.0]
    cuts = [1.01, 2.02, 3.03]
    a = snap_cuts(cuts, onsets, max_shift_ms=50)
    b = snap_cuts(cuts, onsets, max_shift_ms=50)
    assert a == b
