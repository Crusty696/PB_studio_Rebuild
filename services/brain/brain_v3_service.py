"""Brain V3 — In-Process-Service-Fassade (Phase 4, D-034).

5 Methoden fuer den UI-Layer:
    suggest(audio_clip_id, video_clip_ids, n_top)  — Cut-Vorschlaege
    feedback(cut_id, rating)                       — 4-Klick-Event
    learning_session(n=15)                         — Stichproben-Cuts
    stats()                                        — Diagnostik
    reset(confirmation_token)                      — Two-Step-Reset

KEINE REST/HTTP-Endpoints. Aufruf direkt aus PySide6-UI-Layer.

Phase-4-Status: SKELETON. `suggest()` liefert ohne echte
Kandidaten-/Audio-/Pacing-Daten bewusst keine Vorschlaege. Der
`learning_session()`-Fallback bleibt fuer die bestehende Lern-UI erhalten.
"""
from __future__ import annotations

import logging
import secrets
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional

from services.brain import paths
from services.brain.cold_start import BRIDGE_AXES
from services.brain.context_resolver import CutContext, context_keys
from services.brain.feedback_logger import FeedbackLogger
from services.brain.schemas.brain_v3_schemas import (
    BrainV3HealthResponse,
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
from services.brain.storage.brain_store import BrainStore
from services.brain.weight_store import WeightStore, MIN_CONFIDENT_SAMPLES

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
        pattern_notifier: Optional[Callable[[], object]] = None,
    ):
        self._brain_store = brain_store or BrainStore()
        self._weight_store = weight_store or WeightStore(self._brain_store.weights_path)
        self._feedback_logger = FeedbackLogger(self._weight_store)
        self._reset_state = _ResetTokenState()
        self._project_root = Path(project_root) if project_root is not None else None
        self._session_factory = session_factory
        # B-737: Brain-Feedback muss auch das Muster-Lernen anstossen. Default
        # ist der modulweite MemoryUpdaterWorker; Tests injizieren einen Fake.
        self._pattern_notifier = pattern_notifier

    def suggest(self, request: SuggestRequest) -> SuggestResponse:
        """Fail-closed bis echte Ranking-Eingaben an dieser API anliegen.

        ``SuggestRequest`` traegt nur IDs. Daraus lassen sich weder fachliche
        Kandidatenmerkmale noch Audio- oder Pacing-Kontext ableiten. IDs oder
        Listenpositionen duerfen deshalb keine scheinbare Rangliste erzeugen.
        """
        requested_video_clip_count = len(request.video_clip_ids)
        logger.warning(
            "BrainV3Service.suggest: keine echten Ranking-Eingaben "
            "(audio=%d, n_video=%d); fail-closed",
            request.audio_clip_id,
            requested_video_clip_count,
        )
        return SuggestResponse(
            cuts=[],
            used_brain_v3=False,
            explanation={
                "phase4_status": "unavailable",
                "reason": "missing_real_ranking_inputs",
                "candidate_count": 0,
                "requested_video_clip_count": requested_video_clip_count,
            },
        )

    # ------------------------------------------------------------------
    # 2. FEEDBACK
    # ------------------------------------------------------------------
    def feedback(
        self,
        request: FeedbackRequest,
        context: Optional[CutContext] = None,
        axis_contributions: Optional[Mapping[str, float]] = None,
    ) -> FeedbackResponse:
        """Verarbeitet einen 4-Klick-Event.

        Args:
            request: cut_id + rating ('perfect'|'fits'|'not_quite'|'no_match')
                + optional ``axis_contributions``.
            context: optional CutContext fuer den Cut. Wenn None, wird ein
                neutraler Default-Context verwendet (Cold-Start-Bucket).
            axis_contributions: B-732 — Beitrag pro Bridge-Achse an genau
                DIESER Entscheidung. Hat Vorrang vor
                ``request.axis_contributions`` (Keyword-Aufrufer schlagen den
                Request). Fehlt beides, laeuft der Klick bewusst in den
                markierten Uniform-Pfad des FeedbackLoggers — der kann die
                Kandidaten-Reihenfolge mathematisch nicht veraendern.

        Returns:
            FeedbackResponse mit n_buckets_updated, credit_mode und
            n_axes_credited.
        """
        ctx = context or CutContext()
        keys_by_level = context_keys(ctx)
        contribs = axis_contributions
        if contribs is None:
            contribs = getattr(request, "axis_contributions", None)
        # H-12: Schreibpfad prozessweit serialisieren. Ohne Lock koennen
        # parallele feedback()-Aufrufe (a) auf einer geteilten Instanz die
        # BEGIN..COMMIT-Transaktion auf der gecachten Connection verschraenken
        # ("cannot start a transaction within a transaction") und (b) ueber
        # mehrere Instanzen WAL-Write-Contention auf weights.db erzeugen.
        with _FEEDBACK_WRITE_LOCK:
            diag = self._feedback_logger.log_feedback(
                request.rating,
                keys_by_level,
                axis_contributions=contribs,
            )
        self._notify_pattern_learning()
        return FeedbackResponse(
            cut_id=request.cut_id,
            rating=request.rating,
            n_buckets_updated=diag.get("n_buckets_updated", 0),
            alpha_delta=diag.get("alpha_delta", 0.0),
            beta_delta=diag.get("beta_delta", 0.0),
            credit_mode=diag.get("credit_mode", "uniform"),
            n_axes_credited=int(diag.get("n_axes_credited", 0)),
        )

    def _notify_pattern_learning(self) -> None:
        """B-737: Brain-Feedback an das Muster-Lernen koppeln.

        Der 4-Klick-Pfad schrieb bisher nur in ``weights.db``. Der
        PatternAggregator (``mem_learned_pattern``) wurde ausschliesslich vom
        Verdict-Pfad in ``ui/timeline.py`` angestossen — ein Klick im
        Feedback-Popup oder in der Lern-Session erreichte ihn nie.

        Best-effort: Fehler werden geloggt, nie geraised. Feedback darf die
        UI nicht crashen, nur weil die Aggregation nicht bereitsteht.
        """
        notifier = self._pattern_notifier
        try:
            if notifier is None:
                from workers.memory_updater import get_memory_updater

                notifier = get_memory_updater().notify_feedback
            notifier()
        except Exception as exc:  # broad: Lernkreis darf UI nicht killen
            logger.debug(
                "BrainV3Service: Muster-Lernen nicht benachrichtigt: %s", exc,
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
        from services.brain.timeline_state import load_learning_preview_samples

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

        from services.brain.smart_sampler import sample_uncertain
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
        from services.brain.storage.embedding_cache import EmbeddingCache

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
