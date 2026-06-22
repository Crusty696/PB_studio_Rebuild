"""Plan: AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17.

T1.2: AudioAnalysisPipeline - strict-sequential Orchestrator.

A-3 Threading: QObject auf Main-UI-Thread, run() scheduled QRunnable
auf QThreadPool.globalInstance(). Signals Cross-Thread-safe via
QueuedConnection (Default fuer QObjects mit Affinity).

A-1 Fail-Fast: Stage-Exception -> Pipeline-Stop, kein Fallback.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

from PySide6.QtCore import QObject, Signal, QThreadPool, QRunnable, Slot

from services.audio_pipeline.context import PipelineContext

logger = logging.getLogger(__name__)


class _StageProtocol:
    """Stage-Interface fuer Static-Typing-Doku."""
    name: str
    def run(self, context: PipelineContext) -> None: ...


class _PipelineRunnable(QRunnable):
    """A-3: QRunnable haelt Stage-Loop; laeuft auf QThreadPool-Worker-Thread."""

    def __init__(self, pipeline: "AudioAnalysisPipeline", context: PipelineContext):
        super().__init__()
        self._pipeline = pipeline
        self._context = context

    @Slot()
    def run(self) -> None:
        try:
            self._pipeline._run_stages(self._context)
        except Exception as e:
            # Bereits via stage_failed signaled - hier nur Logging.
            logger.error("Pipeline-Runnable Exception: %s", e, exc_info=True)


class AudioAnalysisPipeline(QObject):
    """Strict-sequential Audio-Analyse-Pipeline.

    Stage-Sequenz hart-kodiert (oder via ctor-Argument fuer Tests).
    Signals:
      - stage_started(name: str)
      - stage_done(name: str, payload: dict)
      - stage_failed(name: str, message: str)
      - pipeline_done(track_id: int)
    """

    stage_started = Signal(str)
    stage_done = Signal(str, object)
    stage_failed = Signal(str, str)
    pipeline_done = Signal(int)

    def __init__(self, stages: Iterable[Any] | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self._stages = list(stages) if stages is not None else []
        self._context: PipelineContext | None = None

    def attach_context(self, context: PipelineContext) -> None:
        """A-6: Context-Referenz fuer snapshot_for_save() halten."""
        self._context = context

    def run(self, context: PipelineContext) -> None:
        """A-3: non-blocking. Scheduled Runnable auf QThreadPool."""
        self.attach_context(context)
        runnable = _PipelineRunnable(self, context)
        QThreadPool.globalInstance().start(runnable)

    def snapshot_for_save(self) -> dict:
        """A-6 / fixt R-12: konsistenter Snapshot von context.results unter save_lock.

        Returns deepcopy; Mutationen am Snapshot beeinflussen Context nicht.
        Wenn kein Context attached: leeres dict.
        """
        import copy
        if self._context is None:
            return {}
        with self._context.save_lock:
            return copy.deepcopy(self._context.results)

    def _run_stages(self, context: PipelineContext) -> None:
        """Synchron-Variante (fuer Tests + interner Runnable-Body).

        T4.2 Resume: Stages mit ``checkpoint.is_stage_done`` werden uebersprungen.
        Nach Success markiert ``checkpoint.mark_stage_done`` den Status (atomic).
        """
        from services.audio_pipeline import checkpoint as _ckpt

        # OTK-018 / BUG-1: stale Checkpoint (fremder Track gleicher track_id, oder
        # geaenderte Datei) verwerfen, sonst werden alle Stages faelschlich als
        # done uebersprungen ("0 Stages", keine DB-Writes).
        _ckpt.invalidate_if_stale(context.track_id, context.original_path)

        for stage in self._stages:
            if context.should_stop and context.should_stop():
                raise RuntimeError("Audio-V2 Pipeline abgebrochen (User-Cancel)")
            name = getattr(stage, "name", stage.__class__.__name__)
            if _ckpt.is_stage_done(context.track_id, name):
                # T4.2: Skip - bereits in vorherigem Lauf erfolgreich.
                # OTK-018: Resume-Rehydration - uebersprungene Stage darf Context
                # noch befuellen (z.B. StemGenStage -> stem_paths), damit
                # nachfolgende stem-geroutete Stages nicht an leerem Context scheitern.
                try:
                    stage.rehydrate(context)
                except Exception as e:
                    logger.warning("Rehydrate von Stage '%s' fehlgeschlagen: %s", name, e)
                self.stage_done.emit(name, {"skipped": True})
                continue
            self.stage_started.emit(name)
            try:
                stage.run(context)
            except Exception as e:
                msg = f"{name} failed: {e}"
                logger.error(msg, exc_info=True)
                self.stage_failed.emit(name, msg)
                # A-1 / AC-9: Fail-fast - keine Fallback, keine weiteren Stages.
                raise
            # T4.2: Checkpoint-Mark NACH Success, atomic.
            _ckpt.mark_stage_done(context.track_id, name)
            payload = context.results.get(name, {})
            self.stage_done.emit(name, payload)
        self.pipeline_done.emit(context.track_id)
