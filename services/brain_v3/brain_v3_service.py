"""Brain V3 — In-Process-Service-Fassade (Phase 4, D-034).

5 Methoden fuer den UI-Layer:
    suggest(audio_clip_id, video_clip_ids, n_top)  — Cut-Vorschlaege
    feedback(cut_id, rating)                       — 4-Klick-Event
    learning_session(n=15)                         — Stichproben-Cuts
    stats()                                        — Diagnostik
    reset(confirmation_token)                      — Two-Step-Reset

KEINE REST/HTTP-Endpoints. Aufruf direkt aus PySide6-UI-Layer.

Phase-4-Status: SKELETON. Reranker (`reranker.py`) + Smart-Sampler
(`smart_sampler.py`) sind Folge-Sub-Tasks. `suggest()` und
`learning_session()` liefern aktuell Stub-Daten + erlauben damit
End-to-End-UI-Integration ohne den vollen Rerank-Pfad.
"""
from __future__ import annotations

import logging
import secrets
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from services.brain_v3 import paths
from services.brain_v3.cold_start import BRIDGE_AXES
from services.brain_v3.context_resolver import CutContext, context_keys
from services.brain_v3.feedback_logger import FeedbackLogger
from services.brain_v3.schemas.brain_v3_schemas import (
    BrainV3HealthResponse,
    CutSuggestion,
    FeedbackRequest,
    FeedbackResponse,
    LearningSampleCut,
    LearningSessionResponse,
    ResetRequest,
    ResetResponse,
    StatsResponse,
    SuggestRequest,
    SuggestResponse,
)
from services.brain_v3.storage.brain_store import BrainStore
from services.brain_v3.weight_store import WeightStore, MIN_CONFIDENT_SAMPLES

logger = logging.getLogger(__name__)

# H-12: Prozessweiter Lock fuer den Feedback-Schreibpfad. Modul-global (nicht
# Instanz-Attribut), weil Caller (z.B. _FeedbackSubmitWorker im UI-Layer) pro
# Worker-Thread eigene Service-Instanzen bauen — alle schreiben aber in
# dieselbe weights.db. RLock serialisiert die BEGIN..COMMIT-Transaktion von
# FeedbackLogger.log_feedback ueber alle Instanzen und Threads hinweg.
_FEEDBACK_WRITE_LOCK = threading.RLock()


@dataclass
class _ResetTokenState:
    token: Optional[str] = None


@dataclass(frozen=True)
class _SuggestClipFeatures:
    clip_id: int
    motion_score: float = 0.5
    embedding: Optional[object] = None


@dataclass(frozen=True)
class _SuggestAudioContext:
    at_section_type: str = "verse"
    at_mood_audio: str = "neutral"
    at_bpm: float = 120.0
    at_energy: float = 0.5
    at_harmonic_tension: float = 0.0


class BrainV3Service:
    """In-process Service-Fassade fuer den Brain-V3-Lern-Algorithmus.

    Lazy-init aller V3-Stores (BrainStore + WeightStore + FeedbackLogger).

    Threading (H-12-Fix): ``feedback()`` ist durch den prozessweiten
    ``_FEEDBACK_WRITE_LOCK`` serialisiert und darf aus beliebigen Threads
    aufgerufen werden — auch ueber mehrere Service-Instanzen hinweg (alle
    schreiben in dieselbe weights.db). Die uebrigen Methoden (suggest,
    learning_session, stats, health, reset) sind weiterhin NICHT
    thread-safe: pro Caller-Thread eine eigene Instanz nutzen (WeightStore
    cached eine sqlite3-Connection).
    """

    def __init__(
        self,
        brain_store: Optional[BrainStore] = None,
        weight_store: Optional[WeightStore] = None,
        project_root: Optional[Path] = None,
        session_factory=None,
    ):
        self._brain_store = brain_store or BrainStore()
        self._weight_store = weight_store or WeightStore(self._brain_store.weights_path)
        self._feedback_logger = FeedbackLogger(self._weight_store)
        self._reset_state = _ResetTokenState()
        self._project_root = Path(project_root) if project_root is not None else None
        self._session_factory = session_factory

    def suggest(self, request: SuggestRequest) -> SuggestResponse:
        """Liefert Top-N Cut-Vorschlaege fuer eine Audio/Video-Kombination.

        Service-Fassade uebergibt eine leichte Kandidatenliste an den
        BrainV3Reranker. Die Pacing-Pipeline bleibt der reichere Live-Pfad;
        dieser In-Process-API-Pfad liefert stabile Top-N-Vorschlaege fuer UI
        und Smoke-Tests.
        """
        if request.n_top <= 0 or not request.video_clip_ids:
            return SuggestResponse(
                cuts=[],
                used_brain_v3=request.use_brain_v3,
                explanation={
                    "phase4_status": "reranker",
                    "reason": "no_candidates",
                },
            )

        logger.info(
            "BrainV3Service.suggest(audio=%d, n_video=%d, n_top=%d, brain=%s)",
            request.audio_clip_id, len(request.video_clip_ids), request.n_top,
            request.use_brain_v3,
        )

        scored = self._build_service_candidates(request.video_clip_ids)
        if request.use_brain_v3:
            try:
                from services.brain_v3.reranker import BrainV3Reranker
                reranked = BrainV3Reranker(
                    self._weight_store,
                    brain_weight=1.0,
                    min_confidence=request.min_confidence,
                ).rerank(scored, _SuggestAudioContext())
                cuts = [
                    self._suggestion_from_reranked(request.audio_clip_id, rank, item)
                    for rank, item in enumerate(reranked[:request.n_top], start=1)
                ]
                return SuggestResponse(
                    cuts=cuts,
                    used_brain_v3=True,
                    explanation={
                        "phase4_status": "reranker",
                        "candidate_count": len(scored),
                        "returned_count": len(cuts),
                    },
                )
            except Exception as exc:
                logger.warning(
                    "BrainV3Service.suggest: reranker failed, fallback soft-score: %s",
                    exc,
                    exc_info=True,
                )

        fallback = sorted(scored, key=lambda row: row[1], reverse=True)
        cuts = [
            CutSuggestion(
                cut_id=f"a{request.audio_clip_id}:v{getattr(clip, 'clip_id')}:r{rank}",
                clip_id=int(getattr(clip, "clip_id")),
                audio_clip_id=request.audio_clip_id,
                score=float(soft_score),
                metadata={
                    "brain_v3_scores": {},
                    "brain_v3_enabled": False,
                    "original_soft_score": float(soft_score),
                },
            )
            for rank, (clip, soft_score, _contribs) in enumerate(
                fallback[:request.n_top], start=1
            )
        ]
        return SuggestResponse(
            cuts=cuts,
            used_brain_v3=False,
            explanation={
                "phase4_status": "fallback",
                "candidate_count": len(scored),
                "returned_count": len(cuts),
            },
        )

    @staticmethod
    def _build_service_candidates(
        video_clip_ids: list[int],
    ) -> list[tuple[_SuggestClipFeatures, float, dict[str, float]]]:
        total = max(1, len(video_clip_ids))
        rows: list[tuple[_SuggestClipFeatures, float, dict[str, float]]] = []
        for idx, clip_id in enumerate(video_clip_ids):
            soft_score = 1.0 - (idx / (total + 1))
            motion = 0.25 + (0.5 * ((idx % 5) / 4.0))
            rows.append((
                _SuggestClipFeatures(clip_id=int(clip_id), motion_score=motion),
                float(soft_score),
                {
                    "duration_s": 1.0,
                    "brightness": 0.5,
                    "saturation": 0.5,
                    "color_temp": 0.0,
                },
            ))
        return rows

    @staticmethod
    def _suggestion_from_reranked(
        audio_clip_id: int,
        rank: int,
        item,
    ) -> CutSuggestion:
        return CutSuggestion(
            cut_id=f"a{audio_clip_id}:v{item.clip_id}:r{rank}",
            clip_id=int(item.clip_id),
            audio_clip_id=audio_clip_id,
            score=float(item.final_score),
            metadata={
                "brain_v3_scores": dict(item.brain_v3_scores),
                "brain_score": float(item.brain_score),
                "original_soft_score": float(item.original_soft_score),
                "rank": rank,
            },
        )

    # ------------------------------------------------------------------
    # 2. FEEDBACK
    # ------------------------------------------------------------------
    def feedback(
        self,
        request: FeedbackRequest,
        context: Optional[CutContext] = None,
    ) -> FeedbackResponse:
        """Verarbeitet einen 4-Klick-Event.

        Args:
            request: cut_id + rating ('perfect'|'fits'|'not_quite'|'no_match').
            context: optional CutContext fuer den Cut. Wenn None, wird ein
                neutraler Default-Context verwendet (Cold-Start-Bucket).

        Returns:
            FeedbackResponse mit n_buckets_updated.
        """
        ctx = context or CutContext()
        keys_by_level = context_keys(ctx)
        # H-12: Schreibpfad prozessweit serialisieren. Ohne Lock koennen
        # parallele feedback()-Aufrufe (a) auf einer geteilten Instanz die
        # BEGIN..COMMIT-Transaktion auf der gecachten Connection verschraenken
        # ("cannot start a transaction within a transaction") und (b) ueber
        # mehrere Instanzen WAL-Write-Contention auf weights.db erzeugen.
        with _FEEDBACK_WRITE_LOCK:
            diag = self._feedback_logger.log_feedback(request.rating, keys_by_level)
        return FeedbackResponse(
            cut_id=request.cut_id,
            rating=request.rating,
            n_buckets_updated=diag.get("n_buckets_updated", 0),
            alpha_delta=diag.get("alpha_delta", 0.0),
            beta_delta=diag.get("beta_delta", 0.0),
        )

    # ------------------------------------------------------------------
    # 3. LEARNING-SESSION
    # ------------------------------------------------------------------
    def learning_session(self, n: int = 15) -> LearningSessionResponse:
        """Liefert n Stichproben-Cuts mit hoher Bayes-Varianz.

        Wenn ein aktueller Projekt-Timeline-State existiert, werden echte
        Timeline-Cuts mit Audio-/Video-Pfaden bevorzugt. Nur wenn keine echten
        Cuts vorhanden sind, faellt der Service auf den Weight-Bucket-Sampler
        ohne Medienpfade zurueck.
        """
        from services.brain_v3.timeline_state import load_learning_preview_samples

        try:
            real_samples = load_learning_preview_samples(
                project_root=self._project_root,
                session_factory=self._session_factory,
                n=n,
            )
        except Exception as exc:
            logger.warning(
                "BrainV3Service.learning_session: real preview resolver failed: %s",
                exc,
                exc_info=True,
            )
            real_samples = []
        if real_samples:
            return LearningSessionResponse(
                samples=real_samples,
                requested_n=n,
                available_n=len(real_samples),
            )

        from services.brain_v3.smart_sampler import sample_uncertain
        points = sample_uncertain(self._weight_store, n=n)
        samples = [
            LearningSampleCut(
                cut_id=hash((p.axis, p.context_level, p.context_key)) & 0x7FFFFFFF,
                audio_position_s=0.0,
                video_position_s=0.0,
                preview_duration_s=0.0,
                clip_id=0,
                has_preview=False,
                uncertainty=min(1.0, p.variance * 4.0),  # rescale ~[0,1]
            )
            for p in points
        ]
        return LearningSessionResponse(
            samples=samples,
            requested_n=n,
            available_n=len(samples),
        )

    # ------------------------------------------------------------------
    # 4. STATS
    # ------------------------------------------------------------------
    def stats(self) -> StatsResponse:
        """Diagnostik fuer den Hirn-V3-Stats-Panel."""
        store_stats = self._brain_store.stats()
        # Cold-Start vs Lerndaten: pro Achse ueberprueft, ob mind. 1 Bucket
        # konfident ist (>=MIN_CONFIDENT_SAMPLES).
        learned, cold = self._count_learned_axes()
        return StatsResponse(
            total_clicks=store_stats.weights_rows,
            cold_start_axes=cold,
            learned_axes=learned,
            top_positive_buckets=self._top_buckets(positive=True, limit=5),
            top_negative_buckets=self._top_buckets(positive=False, limit=5),
            last_feedback_at=self._last_feedback_timestamp(),
        )

    def health(self) -> BrainV3HealthResponse:
        """In-process Health fuer UI/Diagnostik, keine REST-Schicht."""
        from services.brain_v3.storage.embedding_cache import EmbeddingCache

        EmbeddingCache(db_path=paths.embedding_cache_db_path())
        health = self._brain_store.health_check()
        stats = self._brain_store.stats()
        brain_dir = paths.brain_v3_app_dir(create=True)
        brain_dir_lower = str(brain_dir).lower()
        path_consistency_ok = (
            "brain_v3" in brain_dir_lower
            and "brain_v2" not in brain_dir_lower
            and "brain_service" not in brain_dir_lower
        )
        errors = list(health.errors)
        if not path_consistency_ok:
            errors.append(f"Brain-V3-Pfad inkonsistent: {brain_dir}")

        marker = brain_dir / "backups" / "last_weekly_backup.txt"
        last_backup_at: Optional[str] = None
        if marker.exists():
            try:
                last_backup_at = marker.read_text(encoding="utf-8").strip() or None
            except OSError as exc:
                errors.append(f"Backup-Marker unlesbar: {exc}")

        ok = (
            health.weights_ok
            and health.patterns_ok
            and health.embedding_cache_ok
            and path_consistency_ok
            and health.disk_space_mb >= 100
            and not errors
        )
        return BrainV3HealthResponse(
            ok=ok,
            weights_ok=health.weights_ok,
            patterns_ok=health.patterns_ok,
            embedding_cache_ok=health.embedding_cache_ok,
            migrations_version=health.migrations_version,
            disk_space_mb=health.disk_space_mb,
            total_clicks=stats.weights_rows,
            brain_v3_dir=str(brain_dir),
            weights_db=str(self._brain_store.weights_path),
            patterns_db=str(self._brain_store.patterns_path),
            embedding_cache_db=str(paths.embedding_cache_db_path()),
            last_backup_at=last_backup_at,
            path_consistency_ok=path_consistency_ok,
            errors=errors,
        )

    def _count_learned_axes(self) -> tuple[int, int]:
        learned = 0
        for axis in BRIDGE_AXES:
            if self._axis_has_confident_bucket(axis):
                learned += 1
        cold = len(BRIDGE_AXES) - learned
        return learned, cold

    def _axis_has_confident_bucket(self, axis: str) -> bool:
        with self._brain_store.open_weights() as conn:
            row = conn.execute(
                "SELECT MAX(positive_count + negative_count) FROM axis_weights "
                "WHERE axis = ?",
                (axis,),
            ).fetchone()
        if row is None or row[0] is None:
            return False
        return float(row[0]) >= MIN_CONFIDENT_SAMPLES

    def _top_buckets(self, *, positive: bool, limit: int) -> list[dict]:
        order_col = "positive_count" if positive else "negative_count"
        with self._brain_store.open_weights() as conn:
            rows = conn.execute(
                f"SELECT axis, context_level, context_key, "  # nosec B608 - interner Identifier (Tabellen-/Spaltenname aus Code-Konstante), kein User-Input; Query-Werte sind parametrisiert
                f"positive_count, negative_count "
                f"FROM axis_weights "
                f"ORDER BY {order_col} DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "axis": r[0],
                "level": int(r[1]),
                "context_key": r[2],
                "alpha": float(r[3]),
                "beta": float(r[4]),
            }
            for r in rows
        ]

    def _last_feedback_timestamp(self) -> Optional[str]:
        with self._brain_store.open_weights() as conn:
            row = conn.execute(
                "SELECT MAX(last_updated) FROM axis_weights"
            ).fetchone()
        return row[0] if row and row[0] else None

    # ------------------------------------------------------------------
    # 5. RESET (Two-Step)
    # ------------------------------------------------------------------
    def reset(self, request: ResetRequest) -> ResetResponse:
        """Two-Step Reset (06_PHASES.md Z.359-361).

        1. Aufruf ohne `confirmation_token` → Service generiert Token,
           liefert ihn in Response zurueck. Reset NICHT ausgefuehrt.
        2. Aufruf mit demselben Token → Reset wird ausgefuehrt.
           Token wird invalidiert.
        """
        if not request.confirmation_token:
            token = secrets.token_hex(8)
            self._reset_state.token = token
            return ResetResponse(
                status="token_required",
                confirmation_token=token,
            )
        if request.confirmation_token != self._reset_state.token:
            return ResetResponse(
                status="token_required",
                confirmation_token=secrets.token_hex(8),
            )
        # Token gueltig — Reset
        self._reset_state.token = None
        self._brain_store.reset(also_embedding_cache=request.also_embedding_cache)
        cleared = ["axis_weights", "pattern_correlations"]
        if request.also_embedding_cache:
            cleared.append("media_embedding_index")
        logger.warning(
            "BrainV3Service.reset: cleared tables=%s", cleared,
        )
        return ResetResponse(
            status="reset_done",
            cleared_tables=cleared,
        )
