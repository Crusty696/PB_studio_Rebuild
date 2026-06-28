"""Brain V3 — Cold-Start-Defaults aus TriggerSettings + Video-Mitte.

Plan-Doc 05: Bei <10 Samples in jedem Backoff-Level → Fallback auf
diese Default-Werte.
"""
from __future__ import annotations

# 17 Achsen — Reihenfolge ist verbindlich für context_keys + Bucket-Iteration
BRIDGE_AXES: tuple[str, ...] = (
    # 10 Audio-Achsen aus TriggerSettings-Dataclass
    "beat_weight",
    "onset_weight",
    "kick_weight",
    "snare_weight",
    "hihat_weight",
    "energy_weight",
    "energy_threshold",
    "onset_sensitivity",
    "min_clip_length",
    "max_clip_length",
    # 7 Video-Achsen
    "motion_match_weight",
    "scene_cut_weight",
    "brightness_match_weight",
    "color_temp_match_weight",
    "pace_match_weight",
    "semantic_match_weight",
    "mood_match_weight",
)

assert len(BRIDGE_AXES) == 17, "BRIDGE_AXES muss exakt 17 Achsen haben (Plan-Doc 05)"

COLD_START_DEFAULTS: dict[str, float] = {
    # Audio aus TriggerSettings-Defaults
    "beat_weight": 1.0,
    "onset_weight": 0.5,
    "kick_weight": 1.2,
    "snare_weight": 1.0,
    "hihat_weight": 0.3,
    "energy_weight": 0.8,
    "energy_threshold": 0.6,
    "onset_sensitivity": 0.5,
    "min_clip_length": 1.0,
    "max_clip_length": 8.0,
    # Video — neutrale Mitte
    "motion_match_weight": 0.5,
    "scene_cut_weight": 0.5,
    "brightness_match_weight": 0.5,
    "color_temp_match_weight": 0.5,
    "pace_match_weight": 0.5,
    "semantic_match_weight": 0.5,
    "mood_match_weight": 0.5,
}

assert set(COLD_START_DEFAULTS.keys()) == set(BRIDGE_AXES), \
    "COLD_START_DEFAULTS muss exakt die 17 BRIDGE_AXES enthalten"


def get_default(axis: str) -> float:
    """Liefert den Cold-Start-Wert für eine Achse. Wirft KeyError bei unbekannter."""
    if axis not in COLD_START_DEFAULTS:
        raise KeyError(f"Unbekannte Brücken-Achse: {axis!r}. "
                       f"Verfügbar: {sorted(COLD_START_DEFAULTS.keys())}")
    return COLD_START_DEFAULTS[axis]
