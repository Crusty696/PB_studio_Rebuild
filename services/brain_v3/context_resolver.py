"""Brain V3 — ContextResolver (Plan-Doc 05).

6 Kontext-Slots aus Audio/Video-Features ableiten + Quantisierung +
5 Backoff-Keys konstruieren.

Slots:
    audio_section_type        intro|verse|build|drop|break|outro|transition
    audio_subtrack_position   start|middle|end
    audio_energy_level        low|medium|high
    audio_mood                dark|neutral|uplifting
    video_motion_class        low|medium|high|extreme
    video_pace_class          slow|medium|fast

Backoff-Keys (von allgemein zu spezifisch):
    Level 0: ""
    Level 1: "section=...|"
    Level 2: "section=...|mood=...|"
    Level 3: "section=...|mood=...|motion=...|"
    Level 4: "section=...|mood=...|motion=...|energy=...|"
    Level 5: "section=...|mood=...|motion=...|energy=...|pace=...|subpos=...|"
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


VALID_SECTIONS = ("intro", "verse", "build", "drop", "break", "outro", "transition")
VALID_SUBPOS = ("start", "middle", "end")
VALID_ENERGY = ("low", "medium", "high")
VALID_MOOD = ("dark", "neutral", "uplifting")
VALID_MOTION = ("low", "medium", "high", "extreme")
VALID_PACE = ("slow", "medium", "fast")


@dataclass(frozen=True)
class CutContext:
    """Vollständiger Kontext eines Cuts. Quelle für context_keys-Bau."""
    audio_section_type: str = "verse"
    audio_subtrack_position: str = "middle"
    audio_energy_level: str = "medium"
    audio_mood: str = "neutral"
    video_motion_class: str = "medium"
    video_pace_class: str = "medium"
    # Optional: Roh-Features für Bridge-Berechnung (nicht für Backoff-Key)
    raw_audio_features: dict = field(default_factory=dict)
    raw_video_features: dict = field(default_factory=dict)

    def __post_init__(self):
        # Validation
        if self.audio_section_type not in VALID_SECTIONS:
            raise ValueError(f"audio_section_type {self.audio_section_type!r} "
                             f"nicht in {VALID_SECTIONS}")
        if self.audio_subtrack_position not in VALID_SUBPOS:
            raise ValueError(f"audio_subtrack_position {self.audio_subtrack_position!r}")
        if self.audio_energy_level not in VALID_ENERGY:
            raise ValueError(f"audio_energy_level {self.audio_energy_level!r}")
        if self.audio_mood not in VALID_MOOD:
            raise ValueError(f"audio_mood {self.audio_mood!r}")
        if self.video_motion_class not in VALID_MOTION:
            raise ValueError(f"video_motion_class {self.video_motion_class!r}")
        if self.video_pace_class not in VALID_PACE:
            raise ValueError(f"video_pace_class {self.video_pace_class!r}")


def context_keys(cut: CutContext) -> list[str]:
    """Baut die 6-elementige Liste der Backoff-Keys (Level 0..5).

    Reihenfolge: aufsteigend in Spezifität.
    Returns:
        Liste mit genau 6 Strings, [Level0, Level1, ..., Level5].
    """
    l0 = ""
    l1 = f"section={cut.audio_section_type}|"
    l2 = l1 + f"mood={cut.audio_mood}|"
    l3 = l2 + f"motion={cut.video_motion_class}|"
    l4 = l3 + f"energy={cut.audio_energy_level}|"
    l5 = l4 + f"pace={cut.video_pace_class}|subpos={cut.audio_subtrack_position}|"
    return [l0, l1, l2, l3, l4, l5]


def quantize_tertile(value: float, p33: float, p66: float,
                     classes: tuple[str, str, str] = ("low", "medium", "high")) -> str:
    """Tertile-Quantisierung für Energy/Motion-Klassen.

    Args:
        value: zu quantisierender Wert
        p33: 33.-Perzentil-Schwelle
        p66: 66.-Perzentil-Schwelle
        classes: (low_label, mid_label, high_label)
    """
    if value < p33:
        return classes[0]
    if value < p66:
        return classes[1]
    return classes[2]


def quantize_quartile(value: float, p25: float, p50: float, p75: float,
                      classes: tuple[str, str, str, str] = ("low", "medium", "high", "extreme")) -> str:
    """Quartile-Quantisierung fuer 4-Klassen-Variablen (Phase 4, D-036).

    Wird genutzt fuer `video_motion_class` (low/medium/high/extreme) — der
    Tertile-Quantisierer reicht hier nicht. Klassen-Reihenfolge entspricht
    `VALID_MOTION` aus context_resolver.

    Args:
        value: zu quantisierender Wert
        p25/p50/p75: Quartil-Schwellen
        classes: 4-Tupel (lowest, low_mid, high_mid, highest)
    """
    if value < p25:
        return classes[0]
    if value < p50:
        return classes[1]
    if value < p75:
        return classes[2]
    return classes[3]


def quantize_subtrack_position(time_s: float, sub_start_s: float,
                               sub_end_s: float) -> str:
    """Position innerhalb eines Subtracks: start/middle/end.

    start: erste 25 %, middle: 25–75 %, end: letzte 25 %.
    """
    duration = max(1e-6, sub_end_s - sub_start_s)
    rel = (time_s - sub_start_s) / duration
    if rel < 0.25:
        return "start"
    if rel < 0.75:
        return "middle"
    return "end"
