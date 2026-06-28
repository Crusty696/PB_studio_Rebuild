"""Brain V3 Video-Schemas — Pydantic v2.

V3-eigene Erweiterungs-Schemas, getrennt von bestehenden video_schemas.py.
Visual-Curves (Helligkeit, Saettigung, Farbtemperatur) werden default
mit 1 Sample pro Sekunde gesampelt (Plan-Doc 06 Phase 1).
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class CurvePoint(BaseModel):
    """Ein Sample auf einer Visual-Kurve (Brightness, Saturation, ColorTemp)."""
    model_config = ConfigDict(frozen=True)

    time: float = Field(..., ge=0.0, description="Sekunden vom Clip-Start")
    value: float = Field(..., description="Normalisierter Wert (0..1 fuer Brightness/Sat, K fuer ColorTemp)")


class VisualCurves(BaseModel):
    """Pre-computed Brücken-Features fuer einen Video-Clip.

    Plan-Doc 04 Schema 4 ('video_units'): pre-computed motion_score,
    brightness, saturation, color_temp werden hier auf Kurven-Basis
    gehalten (statt nur Mittelwert).
    """
    sample_rate_hz: float = Field(default=1.0, gt=0.0,
                                  description="Sample-Rate der Kurven (default 1 Hz = 1/Sekunde)")
    duration_seconds: float = Field(..., gt=0.0)
    brightness: list[CurvePoint] = Field(default_factory=list)
    saturation: list[CurvePoint] = Field(default_factory=list)
    color_temperature: list[CurvePoint] = Field(default_factory=list,
                                                description="Approximation in arbitrary units (warm-cool ratio)")


class BrainV3VideoMeta(BaseModel):
    """V3-Erweiterung zur bestehenden VideoClipInfo, ueber video_hash verknuepft."""
    video_hash: str = Field(..., min_length=64, max_length=64, description="sha256 hex")
    has_video_embedding_v3: bool = Field(default=False, description="True nach erfolgreichem SigLIP-2-Run")
    visual_curves: Optional[VisualCurves] = None
    # Tag-Felder typisiert getrennt (Plan-Doc 06 Phase 1)
    mood_tags: list[str] = Field(default_factory=list)
    style_tags: list[str] = Field(default_factory=list)
    object_tags: list[str] = Field(default_factory=list)


class VisualCurvesResult(BaseModel):
    """Vollstaendiges Output von VisualCurves-Extractor — fuer Logging + Tests."""
    video_hash: str = Field(..., min_length=64, max_length=64)
    duration_seconds: float = Field(..., gt=0.0)
    sample_rate_hz: float = Field(default=1.0, gt=0.0)
    n_samples: int = Field(..., ge=0)
    curves: VisualCurves
