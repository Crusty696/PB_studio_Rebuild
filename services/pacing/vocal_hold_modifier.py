"""Slice 1 / FR-S1-2: Vocal-on-Hold spacing modifier.

Wenn die Vocal-Stem-Energy einer Section dominant ist, wird der Cut-
Spacing-Multiplikator auf 2.0 angehoben — Schnitte werden seltener,
das Bild "atmet" über die Lyric-Phrase.

Eingabe: Per-Section-Stem-Energien wie sie
`services.pacing.stem_section_aggregator.aggregate()` liefert
(L1-normalisiert, sum=1).
"""
from __future__ import annotations

from typing import Mapping


def vocal_hold_spacing_modifier(
    stem_energies: Mapping[str, float],
    threshold: float = 0.40,
) -> float:
    """1.0 (kein Modifier) oder 2.0 (Vocal-on-Hold aktiv).

    Args:
        stem_energies: Mapping {"vocals": .., "drums": .., ...}.
            Default-Format aus stem_section_aggregator.
        threshold: Vocal-Energie ab der gehalten wird. Default 0.40.
    """
    if not stem_energies:
        return 1.0
    vocal = float(stem_energies.get("vocals", 0.0))
    return 2.0 if vocal >= threshold else 1.0
