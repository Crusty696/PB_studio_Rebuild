"""Brain V3 — Context-Mapping (Phase 4, D-036).

Konfigurierbare Mappings von AudioContext-Slots auf CutContext-Slots.
Defaults laut Plan-Doc 06 Phase 4 Z.328-334:
    chorus → drop
    bridge → transition
    calm → neutral
    dramatic → dark
    ambient → neutral
    pace_source = recent_cuts

YAML-Loader optional via `from_yaml(path)`. Validierung gegen `VALID_*`-
Konstanten aus `context_resolver`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from services.brain.context_resolver import (
    CutContext,
    VALID_SECTIONS,
    VALID_MOOD,
)


# Default-Mappings laut Plan-Doc 06 Phase 4
DEFAULT_SECTION_MAP: dict[str, str] = {
    # AudioContext.section_type -> CutContext.audio_section_type
    "chorus": "drop",
    "bridge": "transition",
    "verse": "verse",
    "intro": "intro",
    "outro": "outro",
    "build": "build",
    "drop": "drop",
    "break": "break",
    "transition": "transition",
}

DEFAULT_MOOD_MAP: dict[str, str] = {
    # raw mood label -> CutContext.audio_mood
    "calm": "neutral",
    "dramatic": "dark",
    "ambient": "neutral",
    "dark": "dark",
    "neutral": "neutral",
    "uplifting": "uplifting",
    "happy": "uplifting",
    "sad": "dark",
    "energetic": "uplifting",
}

DEFAULT_PACE_SOURCE = "recent_cuts"  # alternativ: 'audio_bpm', 'fixed_medium'


@dataclass
class ContextMappingConfig:
    """Mapping-Konfiguration. Override via YAML moeglich."""
    section_map: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_SECTION_MAP))
    mood_map: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_MOOD_MAP))
    pace_source: str = DEFAULT_PACE_SOURCE

    def __post_init__(self) -> None:
        # Validate dass alle Targets in den VALID_*-Listen sind
        for raw, target in self.section_map.items():
            if target not in VALID_SECTIONS:
                raise ValueError(
                    f"section_map[{raw!r}]={target!r} nicht in VALID_SECTIONS={VALID_SECTIONS}"
                )
        for raw, target in self.mood_map.items():
            if target not in VALID_MOOD:
                raise ValueError(
                    f"mood_map[{raw!r}]={target!r} nicht in VALID_MOOD={VALID_MOOD}"
                )
        if self.pace_source not in ("recent_cuts", "audio_bpm", "fixed_medium"):
            raise ValueError(
                f"pace_source={self.pace_source!r} unbekannt"
            )

    @classmethod
    def from_yaml(cls, path: Path | str) -> "ContextMappingConfig":
        """Laedt Konfiguration aus YAML. Fehlende Keys -> Defaults."""
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "PyYAML nicht installiert. Im Workspace ausfuehren: "
                "%PB_PYTHON% -m pip install pyyaml"
            ) from exc
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Context-Mapping-YAML fehlt: {p}")
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return cls(
            section_map={**DEFAULT_SECTION_MAP, **(data.get("section_map") or {})},
            mood_map={**DEFAULT_MOOD_MAP, **(data.get("mood_map") or {})},
            pace_source=data.get("pace_source", DEFAULT_PACE_SOURCE),
        )


def map_section(raw_section: str, cfg: ContextMappingConfig) -> str:
    """Mapped raw audio section auf CutContext.audio_section_type."""
    raw = (raw_section or "").lower().strip()
    return cfg.section_map.get(raw, "verse")


def map_mood(raw_mood: str, cfg: ContextMappingConfig) -> str:
    """Mapped raw mood-label auf CutContext.audio_mood."""
    raw = (raw_mood or "").lower().strip()
    return cfg.mood_map.get(raw, "neutral")


def derive_pace_class(
    cfg: ContextMappingConfig,
    *,
    recent_cut_count: Optional[int] = None,
    audio_bpm: Optional[float] = None,
) -> str:
    """Liefert CutContext.video_pace_class abhaengig von pace_source."""
    if cfg.pace_source == "fixed_medium":
        return "medium"
    if cfg.pace_source == "audio_bpm":
        if audio_bpm is None:
            return "medium"
        if audio_bpm < 100:
            return "slow"
        if audio_bpm < 130:
            return "medium"
        return "fast"
    # recent_cuts: schnell wenn viele kurze Cuts, langsam wenn lange Cuts
    if recent_cut_count is None:
        return "medium"
    if recent_cut_count <= 2:
        return "slow"
    if recent_cut_count <= 5:
        return "medium"
    return "fast"


def build_cut_context(
    *,
    raw_section: str,
    raw_mood: str,
    raw_subtrack_position: str,
    raw_energy_level: str,
    raw_motion_class: str,
    cfg: ContextMappingConfig,
    recent_cut_count: Optional[int] = None,
    audio_bpm: Optional[float] = None,
    raw_audio_features: Optional[dict] = None,
    raw_video_features: Optional[dict] = None,
) -> CutContext:
    """Baut CutContext aus Roh-Werten via konfigurierbarem Mapping.

    Plan-Doc 06 Phase 4 Z.336-340: orchestriert die 6 Slot-Befuellungen.
    Energy/Subpos/Motion erwarten bereits gueltige Werte (durch quantize_*
    vorab quantisiert). Section + Mood gehen durch das Mapping.
    """
    return CutContext(
        audio_section_type=map_section(raw_section, cfg),
        audio_subtrack_position=raw_subtrack_position,
        audio_energy_level=raw_energy_level,
        audio_mood=map_mood(raw_mood, cfg),
        video_motion_class=raw_motion_class,
        video_pace_class=derive_pace_class(
            cfg, recent_cut_count=recent_cut_count, audio_bpm=audio_bpm,
        ),
        raw_audio_features=raw_audio_features or {},
        raw_video_features=raw_video_features or {},
    )
