"""Cross-Modal-Stage.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 39 Stage

Liest scenes.json (Video) + V2-Audio-Outputs (von extern uebergeben) -> cut_plan.json.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from services.video_pipeline.stages.base import StageResult
from services.video_pipeline.stages.cross_modal_alignment import (
    CrossModalAlignmentService,
)


__all__ = ["CrossModalStage"]


class CrossModalStage:
    stage_id = "cross_modal"

    def __init__(
        self,
        *,
        service: CrossModalAlignmentService | None = None,
        audio_outputs_dir: Path | None = None,
    ):
        """
        Args:
            service: CrossModalAlignmentService (default heuristisch).
            audio_outputs_dir: Pfad zu V2-Audio-Output-Dateien.
                               Erwartete Dateien: beats.json, sections.json (optional),
                               drops.json (optional).
        """
        self.service = service or CrossModalAlignmentService()
        self.audio_outputs_dir = audio_outputs_dir

    def run(
        self,
        source_path: Path,
        storage_dir: Path,
        *,
        cancel_token: Any | None = None,
    ) -> StageResult:
        storage_dir = Path(storage_dir)
        scenes_json = storage_dir / "scenes.json"
        if not scenes_json.exists():
            return StageResult(
                stage_id=self.stage_id, status="failed", duration_s=0.0,
                error=f"scenes.json missing: {scenes_json}",
            )
        scenes = json.loads(scenes_json.read_text())

        if self.audio_outputs_dir is None:
            return StageResult(
                stage_id=self.stage_id, status="skipped", duration_s=0.0,
                metrics={"reason": "audio_outputs_dir not provided (V2 not ready)"},
            )

        audio_dir = Path(self.audio_outputs_dir)
        beats_p = audio_dir / "beats.json"
        if not beats_p.exists():
            return StageResult(
                stage_id=self.stage_id, status="skipped", duration_s=0.0,
                metrics={"reason": "beats.json missing"},
            )

        beats_raw = json.loads(beats_p.read_text())
        # Akzeptiere [floats] ODER [{"time_s": x}, ...]
        if beats_raw and isinstance(beats_raw[0], dict):
            beats = [float(b.get("time_s", b.get("t", 0.0))) for b in beats_raw]
        else:
            beats = [float(b) for b in beats_raw]

        sections = None
        drops = None
        sec_p = audio_dir / "sections.json"
        if sec_p.exists():
            sections = json.loads(sec_p.read_text())
        drop_p = audio_dir / "drops.json"
        if drop_p.exists():
            drops_raw = json.loads(drop_p.read_text())
            if drops_raw and isinstance(drops_raw[0], dict):
                drops = [float(d.get("time_s", d.get("t", 0.0))) for d in drops_raw]
            else:
                drops = [float(d) for d in drops_raw]

        t0 = time.monotonic()
        suggestions = self.service.align(
            scenes=scenes, beats=beats, sections=sections, drops=drops,
        )
        out = storage_dir / "cut_plan.json"
        self.service.save_plan(suggestions, out)

        return StageResult(
            stage_id=self.stage_id, status="done",
            duration_s=time.monotonic() - t0,
            artifacts={"cut_plan_json": out},
            metrics={"suggestions": len(suggestions)},
        )
