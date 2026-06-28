"""Brain V3 Audio-Schemas — Pydantic v2 (Workspace nutzt 2.12.x).

V3-eigene Erweiterungs-Schemas, die NICHT in den bestehenden
schemas/audio_schemas.py einflieszen. Statt dessen verknuepfen wir
ueber media_hash mit der bestehenden AudioClipInfo.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class SubtrackSegment(BaseModel):
    """Ein detektierter Sub-Track innerhalb eines DJ-Mix.

    Phase 1 / Plan-Doc 04 Schema 5 ('audio_units' level=section).
    """
    model_config = ConfigDict(frozen=True)  # immutable, hashable

    start_time: float = Field(..., ge=0.0, description="Sekunden vom Mix-Start")
    end_time: float = Field(..., gt=0.0, description="Sekunden vom Mix-Start, > start_time")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Fusion-Score 0..1 aus 4 Signalen")
    sub_bpm: Optional[float] = Field(None, gt=0.0, description="Lokale BPM in diesem Segment, optional")
    sub_key: Optional[str] = Field(None, description="Lokale Tonart (z.B. 'C maj'), optional")

    def duration(self) -> float:
        return self.end_time - self.start_time


class TempoCurvePoint(BaseModel):
    """Sliding-Window-BPM-Sample. Default 5 s Schritt-weite ueber den Mix."""
    model_config = ConfigDict(frozen=True)

    time: float = Field(..., ge=0.0)
    bpm: float = Field(..., gt=0.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class BrainV3AudioMeta(BaseModel):
    """V3-Erweiterung zur bestehenden AudioClipInfo, ueber audio_hash verknuepft.

    Persistiert in projekt-spezifischer state.db (Plan-Doc 04 Schema 5).
    Hash wird beim Audio-Import per services.brain.hashing.compute_media_hash
    berechnet und hier abgelegt.
    """
    audio_hash: str = Field(..., min_length=64, max_length=64, description="sha256 hex")
    has_audio_embedding_v3: bool = Field(default=False, description="True nach erfolgreichem CLAP-Run")
    subtrack_segments: list[SubtrackSegment] = Field(default_factory=list)
    tempo_curve: list[TempoCurvePoint] = Field(default_factory=list)


class SubtrackDetectionResult(BaseModel):
    """Vollstaendiges Output des SubtrackDetector — fuer Logging + Tests."""
    audio_hash: str = Field(..., min_length=64, max_length=64)
    duration_seconds: float = Field(..., gt=0.0)
    n_segments: int = Field(..., ge=0)
    segments: list[SubtrackSegment] = Field(default_factory=list)
    fusion_weights: dict[str, float] = Field(
        default_factory=lambda: {"foote": 0.35, "stem": 0.30,
                                 "tempo": 0.20, "spectral": 0.15},
        description="Plan-Doc 06 Phase 1 Default-Gewichte",
    )
    fallback_used: bool = Field(
        default=False,
        description="True wenn 0 Boundaries gefunden → Mix als 1 Sub-Track behandelt",
    )
