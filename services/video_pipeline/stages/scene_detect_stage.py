"""Scene-Detect-Stage.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 34 (Tier 3 Workspace+Services)
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from services.video_pipeline.primitives.scene_detect import detect_scenes
from services.video_pipeline.stages.base import StageResult


__all__ = ["SceneDetectStage"]


class SceneDetectStage:
    stage_id = "scene_detect"

    def __init__(self, *, threshold: float = 27.0):
        self.threshold = threshold

    def run(
        self,
        source_path: Path,
        storage_dir: Path,
        *,
        cancel_token: Any | None = None,
    ) -> StageResult:
        source_path = Path(source_path)
        storage_dir = Path(storage_dir)
        storage_dir.mkdir(parents=True, exist_ok=True)
        out_json = storage_dir / "scenes.json"

        t0 = time.monotonic()
        try:
            scenes = detect_scenes(source_path, threshold=self.threshold)
        except Exception as ex:
            return StageResult(
                stage_id=self.stage_id, status="failed",
                duration_s=time.monotonic() - t0, error=str(ex),
            )

        payload = [
            {"index": s.index, "start_s": s.start_s, "end_s": s.end_s,
             "duration_s": s.duration_s}
            for s in scenes
        ]
        out_json.write_text(json.dumps(payload, indent=2))

        return StageResult(
            stage_id=self.stage_id,
            status="done",
            duration_s=time.monotonic() - t0,
            artifacts={"scenes_json": out_json},
            metrics={"scene_count": len(scenes)},
        )
