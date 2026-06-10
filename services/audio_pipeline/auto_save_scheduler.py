"""Plan: AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17.

T5.5: AutoSaveScheduler - Q-B / A-6 Auto-Save 60s + post-Stage.

QTimer 60s + Slot an pipeline.stage_done.
Guard: project_open AND pipeline.is_running.
Ruft ProjectManager.save_project_full(target_path=None) in-place.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal, Slot


DEFAULT_AUTO_SAVE_INTERVAL_MS = 60_000  # 60 s


class AutoSaveScheduler(QObject):
    """Auto-Save 60s-Tick + post-Stage-Tick.

    Verkabelung im Controller:
      scheduler.attach_pipeline(pipeline)
      scheduler.set_project_open_check(lambda: ...)
      scheduler.start()
    """

    saved = Signal(str)  # last_saved_at HH:MM

    def __init__(self, save_callable: Callable[[], object],
                 interval_ms: int = DEFAULT_AUTO_SAVE_INTERVAL_MS,
                 parent: QObject | None = None):
        super().__init__(parent)
        self._save_callable = save_callable
        self._interval_ms = interval_ms
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._on_tick)
        self._project_open_check: Callable[[], bool] = lambda: False
        self._pipeline_running_check: Callable[[], bool] = lambda: False

    def set_project_open_check(self, fn: Callable[[], bool]) -> None:
        self._project_open_check = fn

    def set_pipeline_running_check(self, fn: Callable[[], bool]) -> None:
        self._pipeline_running_check = fn

    def attach_pipeline(self, pipeline) -> None:
        """Verbindet stage_done -> _on_stage_done."""
        try:
            pipeline.stage_done.connect(self._on_stage_done)
        except AttributeError:
            pass

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    @Slot()
    def _on_tick(self) -> None:
        if self._project_open_check() and self._pipeline_running_check():
            self._fire_save()

    @Slot(str, object)
    def _on_stage_done(self, _name: str, _payload) -> None:
        if self._project_open_check():
            self._fire_save()

    def _fire_save(self) -> None:
        try:
            self._save_callable()
            from datetime import datetime
            self.saved.emit(datetime.now().strftime("%H:%M"))
        except Exception:
            # Auto-Save darf Pipeline NICHT crashen.
            import logging
            logging.getLogger(__name__).warning("Auto-Save failed", exc_info=True)
