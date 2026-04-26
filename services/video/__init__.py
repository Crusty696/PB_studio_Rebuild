"""services.video — Aggregator-Index für Video-Domain Services.

Cycle 14 / Option C: Logische Gruppierung der Video-Services ohne
physische Moves. Vorhandene Imports bleiben kompatibel.
"""
from __future__ import annotations

from services.video_service import VideoAnalyzer  # noqa: F401
from services.video_analysis_service import (  # noqa: F401
    SceneInfo,
    PipelineResult,
    detect_scenes,
    generate_embeddings,
    text_to_embedding,
    texts_to_embeddings_batch,
)
from services.vector_db_service import VectorDBService  # noqa: F401

__all__ = [
    "VideoAnalyzer",
    "SceneInfo",
    "PipelineResult",
    "detect_scenes",
    "generate_embeddings",
    "text_to_embedding",
    "texts_to_embeddings_batch",
    "VectorDBService",
]
