"""PacingProfile — Single Source of Truth fuer Pacing-Parameter (SCHNITT Redesign 2026-05-09)."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from services.pacing_service import AdvancedPacingSettings

_CUT_RATE_INDEX_TO_BEATS = {0: 1, 1: 2, 2: 4, 3: 8, 4: 16}

# T4.3 D8: Single Source of Truth fuer breakdown-Werte. ui_binder.PacingProfileBinder
# importiert von hier statt eigene Listen zu pflegen.
BREAKDOWN_CHOICES: tuple[str, ...] = ("halve", "force16", "none")

_PRESETS = {
    "Techno":     {"cut_rate_index": 2, "energy_reactivity": 70, "breakdown": "halve"},
    "Cinematic":  {"cut_rate_index": 4, "energy_reactivity": 30, "breakdown": "none"},
    "House":      {"cut_rate_index": 3, "energy_reactivity": 50, "breakdown": "halve"},
    "Festival":   {"cut_rate_index": 1, "energy_reactivity": 90, "breakdown": "halve"},
}


@dataclass(slots=True)
class ClipAnchorRef:
    anchor_id: int
    time_offset: float
    label: Optional[str] = None


@dataclass(slots=True)
class PacingProfile:
    audio_id: Optional[int] = None
    video_id: Optional[int] = None
    vibe: str = ""
    cut_rate_index: int = 2
    style_preset: str = "Standard"
    energy_reactivity: int = 50
    breakdown: str = "halve"
    manual_density_curve: Optional[list[float]] = None
    anchors: list[ClipAnchorRef] = field(default_factory=list)

    @classmethod
    def from_preset(cls, key: str) -> "PacingProfile":
        if key not in _PRESETS:
            raise ValueError(f"Unbekanntes Preset: {key}")
        cfg = _PRESETS[key]
        return cls(
            cut_rate_index=cfg["cut_rate_index"],
            energy_reactivity=cfg["energy_reactivity"],
            breakdown=cfg["breakdown"],
            style_preset=key,
        )

    def to_advanced_settings(self) -> AdvancedPacingSettings:
        beats = _CUT_RATE_INDEX_TO_BEATS.get(self.cut_rate_index, 4)
        return AdvancedPacingSettings(
            base_cut_rate=beats,
            energy_reactivity=self.energy_reactivity,
            breakdown_behavior=self.breakdown,
            vibe=self.vibe,
            manual_density_curve=self.manual_density_curve,
            anchors=[a for a in self.anchors],
        )
