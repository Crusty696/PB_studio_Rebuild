from __future__ import annotations
from typing import Any, Callable, Optional
from pathlib import Path

from services.brain.legacy_sqlite import BrainService
from services.brain.brain_v3_service import BrainV3Service
from services.brain.schemas.brain_v3_schemas import (
    SuggestRequest,
    SuggestResponse,
    FeedbackRequest,
    FeedbackResponse,
    LearningSessionResponse,
    StatsResponse,
    BrainV3HealthResponse,
    ResetRequest,
    ResetResponse,
)
from services.brain.context_resolver import CutContext


class StudioBrain:
    """Zentrale Backend-Fassade fuer alle Gehirn-Aktivitaeten (V1 SQLite + V3 Vektorsuche).

    Erlaubt dem UI-Layer und Controllern, alle relationalen Abfragen (V1) und
    alle mathematischen/neuronalen Inferenz-Abfragen (V3) ueber eine einzige
    Klasse anzusteuern.
    """

    def __init__(
        self,
        session_factory: Callable[[], Any],
        project_root: Optional[Path] = None,
    ) -> None:
        self._sqlite = BrainService(session_factory)
        self._v3 = BrainV3Service(project_root=project_root, session_factory=session_factory)

    @property
    def sqlite(self) -> BrainService:
        """Direkter Zugriff auf den relationalen Lese-Service (V1)."""
        return self._sqlite

    @property
    def v3(self) -> BrainV3Service:
        """Direkter Zugriff auf den neuronalen Service (V3)."""
        return self._v3

    # --- Delegierte Lese-Methoden von V1 (SQLite) ---
    def invalidate(self) -> None:
        self._sqlite.invalidate()

    def list_scene_count(self) -> int:
        return self._sqlite.list_scene_count()

    def list_active_style_buckets(self) -> list[dict[str, Any]]:
        return self._sqlite.list_active_style_buckets()

    def list_distinct_roles(self) -> list[str]:
        return self._sqlite.list_distinct_roles()

    def list_distinct_moods(self) -> list[str]:
        return self._sqlite.list_distinct_moods()

    def list_clips_with_tags(
        self,
        role: Optional[str] = None,
        mood: Optional[str] = None,
        style_bucket_id: Optional[int] = None,
        min_role_confidence: float = 0.0,
        min_usage_count: int = 0,
    ) -> list[dict[str, Any]]:
        return self._sqlite.list_clips_with_tags(
            role=role,
            mood=mood,
            style_bucket_id=style_bucket_id,
            min_role_confidence=min_role_confidence,
            min_usage_count=min_usage_count,
        )

    def get_clip_detail(self, scene_id: int) -> Optional[dict[str, Any]]:
        return self._sqlite.get_clip_detail(scene_id)

    def structure_stats(self) -> dict[str, Any]:
        return self._sqlite.structure_stats()

    def graph_nodes_and_edges(self) -> dict[str, Any]:
        return self._sqlite.graph_nodes_and_edges()

    # --- Delegierte Methoden von V3 (Neuronales System & Bayes-Lernen) ---
    def suggest(self, request: SuggestRequest) -> SuggestResponse:
        return self._v3.suggest(request)

    def feedback(
        self,
        request: FeedbackRequest,
        context: Optional[CutContext] = None,
    ) -> FeedbackResponse:
        return self._v3.feedback(request, context)

    def learning_session(self, n: int = 15) -> LearningSessionResponse:
        return self._v3.learning_session(n)

    def stats(self) -> StatsResponse:
        return self._v3.stats()

    def health(self) -> BrainV3HealthResponse:
        return self._v3.health()

    def reset(self, request: ResetRequest) -> ResetResponse:
        return self._v3.reset(request)
