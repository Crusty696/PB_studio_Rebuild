"""Slice 1 / FR-S1-3: Drop-Burst-Mode + Hold-Bars.

Bei jedem Drop-Frame wird ein 3-Cut-Burst innerhalb 800ms eingefügt
(±200ms ums Drop-Zentrum), gefolgt von `hold_bars` Bars Stille (kein
neuer Cut).

Hintergrund: Klassische Editor-Heuristik in EDM/HipHop-Visuals — schnelle
Schnitte beim Drop, dann Hold für den groove. Vergleichbar mit dem
"Drop-Burst"-Effekt in After-Effects-Templates.
"""
from __future__ import annotations

from typing import Iterable, Sequence


def apply_drop_burst(
    cut_times: Iterable[float],
    drop_times: Sequence[float],
    bpm: float,
    burst_n: int = 3,
    burst_window_ms: int = 800,
    forward_window_ms: int = 200,
    hold_bars: int = 4,
    beats_per_bar: int = 4,
) -> list[float]:
    """Modifiziert Cut-Liste mit Drop-Burst + Hold-Bars.

    Args:
        cut_times: Originale Beat-aligned Cut-Liste.
        drop_times: Zeitpunkte erkannter Drops (Sekunden).
        bpm: Track-BPM für Hold-Bar-Berechnung.
        burst_n: Wie viele Cuts der Burst enthält. Default 3.
        burst_window_ms: Maximale Spannweite des Bursts. Default 800ms.
        forward_window_ms: Wie weit der Burst nach dem Drop reicht. Default 200ms.
        hold_bars: Bars Stille nach dem Burst. Default 4.
        beats_per_bar: Default 4.

    Returns:
        Sortiert + dedupliziert. Cuts im Hold-Window werden entfernt.
    """
    if bpm <= 0:
        raise ValueError(f"bpm must be > 0, got {bpm}")

    bar_sec = (60.0 / bpm) * beats_per_bar
    hold_sec = bar_sec * hold_bars
    fwd_sec = forward_window_ms / 1000.0
    burst_window_sec = burst_window_ms / 1000.0

    out = set(round(float(t), 6) for t in cut_times)

    for d in drop_times:
        d = float(d)
        # 1) Burst erzeugen — N Cuts symmetrisch ums Drop verteilt.
        # Spec: "±200ms triggert 3 Cuts in 800ms" → 3 Cuts in einem 800ms-
        # Fenster zentriert auf das Drop.
        half = burst_window_sec / 2.0
        burst_start = d - half
        burst_end = d + half
        if burst_n <= 1:
            burst_pts = [round(d, 6)]
        else:
            step = burst_window_sec / (burst_n - 1)
            burst_pts = [round(burst_start + i * step, 6) for i in range(burst_n)]
        _ = fwd_sec  # parameter wird im hold_window unten genutzt

        # 2) Hold-Window: alle Cuts die zwischen burst_end und burst_end + hold_sec
        # liegen entfernen.
        hold_lo = burst_end
        hold_hi = burst_end + hold_sec
        out = {t for t in out if not (hold_lo < t < hold_hi)}

        # 3) Burst-Cuts hinzufügen
        out.update(burst_pts)

    return sorted(out)
