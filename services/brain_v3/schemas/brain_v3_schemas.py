"""Brain V3 — In-Process-Service-Schemas (Phase 4, D-034).

Pydantic v2 Request/Response-Dataclasses fuer `BrainV3Service`.
KEINE REST/HTTP-Schemas — reine Aufruf-/Rueckgabe-Typen, da V3
in-process aufgerufen wird (PySide6 -> Service direkt).
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


RatingLiteral = Literal["perfect", "fits", "not_quite", "no_match"]


class CutSuggestion(BaseModel):
    """Ein vorgeschlagener Cut fuer eine bestimmte Audio-Position."""
    model_config = ConfigDict(frozen=True)

    cut_id: str = Field(..., description="Stable Cut-Identifier (clip+position)")
    clip_id: int
    audio_clip_id: int
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict,
                                     description="Enthaelt brain_v3_scores")


class SuggestRequest(BaseModel):
    audio_clip_id: int
    video_clip_ids: list[int] = Field(default_factory=list)
    n_top: int = 5
    use_brain_v3: bool = True
    min_confidence: float = 0.0


class SuggestResponse(BaseModel):
    cuts: list[CutSuggestion]
    used_brain_v3: bool
    explanation: dict[str, Any] = Field(default_factory=dict)


class FeedbackRequest(BaseModel):
    cut_id: int = Field(..., description="DB-Row-ID aus timeline_cuts.id")
    rating: RatingLiteral


class FeedbackResponse(BaseModel):
    cut_id: int
    rating: RatingLiteral
    n_buckets_updated: int = Field(..., ge=0,
                                   description="Anzahl axis_weights-Updates "
                                               "(17 Achsen x 6 Levels = 102 max)")
    alpha_delta: float
    beta_delta: float


class LearningSampleCut(BaseModel):
    cut_id: int
    audio_position_s: float
    video_position_s: float = 0.0
    preview_duration_s: float = 0.0
    clip_id: int
    audio_preview_path: Optional[str] = None
    video_preview_path: Optional[str] = None
    has_preview: bool = False
    uncertainty: float = Field(..., ge=0.0, le=1.0)


class LearningSessionResponse(BaseModel):
    samples: list[LearningSampleCut]
    requested_n: int
    available_n: int


class StatsResponse(BaseModel):
    total_clicks: int
    cold_start_axes: int = Field(..., ge=0, le=17)
    learned_axes: int = Field(..., ge=0, le=17)
    top_positive_buckets: list[dict[str, Any]] = Field(default_factory=list)
    top_negative_buckets: list[dict[str, Any]] = Field(default_factory=list)
    last_feedback_at: Optional[str] = None


class BrainV3HealthResponse(BaseModel):
    ok: bool
    weights_ok: bool
    patterns_ok: bool
    embedding_cache_ok: bool
    migrations_version: int
    disk_space_mb: int
    total_clicks: int
    brain_v3_dir: str
    weights_db: str
    patterns_db: str
    embedding_cache_db: str
    last_backup_at: Optional[str] = None
    path_consistency_ok: bool
    errors: list[str] = Field(default_factory=list)


class ResetRequest(BaseModel):
    confirmation_token: Optional[str] = None
    also_embedding_cache: bool = False


class ResetResponse(BaseModel):
    status: Literal["token_required", "reset_done"]
    confirmation_token: Optional[str] = None
    cleared_tables: list[str] = Field(default_factory=list)
