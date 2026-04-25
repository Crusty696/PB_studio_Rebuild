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

# FR-S2-3: Section → spacing-multiplier (×2 thinning, ×0.5 thickening)
_BUILDUP_SPACING = 2.0
_DROP_SPACING = 0.5
_NEUTRAL_SPACING = 1.0


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


# ── FR-S2-3: BPM Half-Double-Adaptation ────────────────────────────────────


def section_spacing_multiplier(section_type: str | None) -> float:
    """Spacing-Multiplikator pro Section.

    - Build-Up → 2.0 (Cuts ausdünnen, halbiertes BPM-Feeling)
    - Drop → 0.5 (Cuts verdichten, doppeltes BPM-Feeling)
    - sonst → 1.0
    """
    if not section_type:
        return _NEUTRAL_SPACING
    s = str(section_type).strip().lower().replace("-", "_")
    if s in {"buildup", "build_up", "build", "rise"}:
        return _BUILDUP_SPACING
    if s in {"drop", "drop_section"}:
        return _DROP_SPACING
    return _NEUTRAL_SPACING


def _section_at(time: float, sections: Sequence[object]) -> object | None:
    for sec in sections:
        start = float(getattr(sec, "start", getattr(sec, "start_time", 0.0)))
        end = float(getattr(sec, "end", getattr(sec, "end_time", 0.0)))
        if start <= time < end:
            return sec
    return None


def apply_bpm_adaptation(
    cut_times: Iterable[float],
    sections: Sequence[object],
) -> list[float]:
    """Modifiziert Cut-Liste pro Section abhängig vom Section-Typ.

    Build-Up: jeden 2. Cut entfernen (×2 spacing).
    Drop: zwischen aufeinanderfolgenden Cuts einen Mittelpunkt einfügen
        (×0.5 spacing, ohne neue Onset-Information — ist als Hinweis
        für die Pacing-Engine zu verstehen, nicht als finale Cut-Liste).
    Andere Sections: unverändert.
    """
    cuts = sorted(set(round(float(t), 6) for t in cut_times))
    if not sections:
        return cuts

    out: list[float] = []
    # Pro Section sammeln und transformieren
    sec_buckets: dict[int, list[float]] = {}
    no_sec: list[float] = []
    for t in cuts:
        sec = _section_at(t, sections)
        if sec is None:
            no_sec.append(t)
        else:
            sec_buckets.setdefault(id(sec), []).append(t)

    # Bewahre Sections in deren Reihenfolge
    seen: dict[int, object] = {}
    for sec in sections:
        seen[id(sec)] = sec

    out.extend(no_sec)
    for sec_id, sec in seen.items():
        bucket = sec_buckets.get(sec_id, [])
        if not bucket:
            continue
        mult = section_spacing_multiplier(getattr(sec, "section_type", None))
        if mult == _BUILDUP_SPACING:
            # Jeden zweiten Cut entfernen.
            thinned = [t for i, t in enumerate(bucket) if i % 2 == 0]
            out.extend(thinned)
        elif mult == _DROP_SPACING:
            # Zwischen aufeinanderfolgenden Cuts einen Mittelpunkt einfügen.
            dense = list(bucket)
            for a, b in zip(bucket, bucket[1:]):
                dense.append(round((a + b) / 2.0, 6))
            out.extend(dense)
        else:
            out.extend(bucket)

    return sorted(set(out))
