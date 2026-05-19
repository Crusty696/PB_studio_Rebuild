"""Status-Reporter (Phase 37).

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 37 (Tier 3 Workspace+Services)

Aggregiert Pipeline-Stage-Events fuer UI-Anzeige. Plain Python — Qt-QObject-Wrapping
in Caller-Migration-Phase. Implementiert ``PipelineListener``-Protokoll.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable


__all__ = ["StageStatus", "StatusReporter"]


@dataclass
class StageStatus:
    stage_id: str
    status: str = "pending"          # pending/running/done/failed/skipped/partial
    started_at: str | None = None
    finished_at: str | None = None
    duration_s: float | None = None
    error: str | None = None
    metrics: dict = field(default_factory=dict)


class StatusReporter:
    """Sammelt Stage-Status-Updates. Bietet Snapshot-Lookup + Listener-Callback."""

    def __init__(self, stage_ids: list[str]):
        self._statuses: dict[str, StageStatus] = {
            sid: StageStatus(stage_id=sid) for sid in stage_ids
        }
        self._listeners: list[Callable[[StageStatus], None]] = []

    def subscribe(self, callback: Callable[[StageStatus], None]) -> None:
        self._listeners.append(callback)

    def _emit(self, status: StageStatus) -> None:
        for cb in self._listeners:
            try:
                cb(status)
            except Exception:
                pass

    def snapshot(self) -> dict[str, StageStatus]:
        return dict(self._statuses)

    def status_of(self, stage_id: str) -> StageStatus:
        return self._statuses[stage_id]

    def progress_summary(self) -> dict[str, int]:
        out = {"total": len(self._statuses), "done": 0, "running": 0,
               "failed": 0, "pending": 0, "partial": 0, "skipped": 0}
        for st in self._statuses.values():
            out[st.status] = out.get(st.status, 0) + 1
        return out

    # PipelineListener-Protokoll

    def on_stage_started(self, track_id: int, stage_id: str) -> None:
        st = self._statuses.setdefault(stage_id, StageStatus(stage_id=stage_id))
        st.status = "running"
        st.started_at = datetime.utcnow().isoformat()
        self._emit(st)

    def on_stage_done(self, track_id: int, result) -> None:
        st = self._statuses.setdefault(result.stage_id, StageStatus(stage_id=result.stage_id))
        st.status = result.status
        st.finished_at = datetime.utcnow().isoformat()
        st.duration_s = result.duration_s
        st.metrics = dict(result.metrics)
        self._emit(st)

    def on_stage_failed(self, track_id: int, result) -> None:
        st = self._statuses.setdefault(result.stage_id, StageStatus(stage_id=result.stage_id))
        st.status = "failed"
        st.finished_at = datetime.utcnow().isoformat()
        st.duration_s = result.duration_s
        st.error = result.error
        st.metrics = dict(result.metrics)
        self._emit(st)

    def on_pipeline_done(self, track_id: int) -> None:
        # nichts zu tun, snapshot bleibt einsehbar
        pass
