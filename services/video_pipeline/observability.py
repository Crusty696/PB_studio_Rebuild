"""Observability — per-stage logging (Phase 71).

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 71 Cross-Cutting

Schreibt JSONL-Eintrag pro Stage-Done/Failed-Event. Caller registriert das
als PipelineListener neben dem StatusReporter.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


__all__ = ["JsonlObserver"]


class JsonlObserver:
    def __init__(self, log_path: Path):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _append(self, payload: dict) -> None:
        with open(self.log_path, "a", encoding="utf-8") as fh:
            json.dump(payload, fh)
            fh.write("\n")

    def on_stage_started(self, track_id: int, stage_id: str) -> None:
        self._append({
            "ts": datetime.utcnow().isoformat(),
            "event": "stage_started",
            "track_id": track_id, "stage_id": stage_id,
        })

    def on_stage_done(self, track_id: int, result) -> None:
        self._append({
            "ts": datetime.utcnow().isoformat(),
            "event": "stage_done",
            "track_id": track_id,
            "stage_id": result.stage_id,
            "status": result.status,
            "duration_s": result.duration_s,
            "metrics": result.metrics,
        })

    def on_stage_failed(self, track_id: int, result) -> None:
        self._append({
            "ts": datetime.utcnow().isoformat(),
            "event": "stage_failed",
            "track_id": track_id,
            "stage_id": result.stage_id,
            "duration_s": result.duration_s,
            "error": result.error,
        })

    def on_pipeline_done(self, track_id: int) -> None:
        self._append({
            "ts": datetime.utcnow().isoformat(),
            "event": "pipeline_done",
            "track_id": track_id,
        })
