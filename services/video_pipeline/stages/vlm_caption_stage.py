"""VLM-Caption-Stage.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 33 Stage
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from services.video_pipeline.stages.base import StageResult
from services.video_pipeline.stages.vlm_caption_service import VlmCaptionService


__all__ = ["VlmCaptionStage"]


class VlmCaptionStage:
    stage_id = "vlm_caption"

    def __init__(
        self,
        *,
        service: VlmCaptionService | None = None,
        frame_filter: str = "scene_anchors",  # "all" | "scene_anchors" | "mid_only"
    ):
        self.service = service or VlmCaptionService()
        self.frame_filter = frame_filter

    def run(
        self,
        source_path: Path,
        storage_dir: Path,
        *,
        cancel_token: Any | None = None,
    ) -> StageResult:
        storage_dir = Path(storage_dir)
        idx_json = storage_dir / "keyframes.json"
        if not idx_json.exists():
            return StageResult(
                stage_id=self.stage_id, status="failed", duration_s=0.0,
                error=f"keyframes.json missing: {idx_json}",
            )

        keyframes = json.loads(idx_json.read_text())
        # Filter
        if self.frame_filter == "mid_only":
            keyframes = [k for k in keyframes if k["role"] == "mid"]
        elif self.frame_filter == "scene_anchors":
            keyframes = [k for k in keyframes if k["role"] in {"start", "mid", "end"}]

        if not keyframes:
            return StageResult(
                stage_id=self.stage_id, status="done", duration_s=0.0,
                metrics={"caption_count": 0},
            )

        t0 = time.monotonic()
        frame_paths = [storage_dir / k["path"] for k in keyframes]
        captions = self.service.caption_keyframes(frame_paths)

        payload = []
        for kf, cap in zip(keyframes, captions):
            payload.append({
                "scene_idx": kf["scene_idx"], "role": kf["role"],
                "time_s": kf["time_s"], "path": kf["path"],
                "text": cap.text, "confidence": cap.confidence,
                "model_id": cap.model_id,
            })

        out_json = storage_dir / "captions.json"
        out_json.write_text(json.dumps(payload, indent=2))

        return StageResult(
            stage_id=self.stage_id, status="done",
            duration_s=time.monotonic() - t0,
            artifacts={"captions_json": out_json},
            metrics={
                "caption_count": len(payload),
                "is_stub": self.service.is_stub,
            },
        )
