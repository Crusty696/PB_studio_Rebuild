"""Keyframe-Extract-Stage.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 35 (Tier 3 Workspace+Services)
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from services.video_pipeline.primitives.decoder import VideoDecoder
from services.video_pipeline.primitives.keyframe_selector import select_keyframes, Keyframe
from services.video_pipeline.primitives.scene_detect import Scene
from services.video_pipeline.stages.base import StageResult


__all__ = ["KeyframeExtractStage"]


class KeyframeExtractStage:
    stage_id = "keyframe_extract"

    def __init__(
        self,
        *,
        mode: str = "anchors_3",
        uniform_every_s: float | None = 2.0,
        jpeg_quality: int = 95,
        decoder: VideoDecoder | None = None,
    ):
        self.mode = mode
        self.uniform_every_s = uniform_every_s
        self.jpeg_quality = jpeg_quality
        self.decoder = decoder or VideoDecoder()

    def run(
        self,
        source_path: Path,
        storage_dir: Path,
        *,
        cancel_token: Any | None = None,
    ) -> StageResult:
        source_path = Path(source_path)
        storage_dir = Path(storage_dir)
        kf_dir = storage_dir / "keyframes"
        kf_dir.mkdir(parents=True, exist_ok=True)

        scenes_json = storage_dir / "scenes.json"
        if not scenes_json.exists():
            return StageResult(
                stage_id=self.stage_id, status="failed",
                duration_s=0.0,
                error=f"scenes.json missing: {scenes_json}",
            )

        scenes_data = json.loads(scenes_json.read_text())
        scenes = [Scene(index=s["index"], start_s=s["start_s"], end_s=s["end_s"])
                  for s in scenes_data]

        keyframes = select_keyframes(
            scenes, mode=self.mode, uniform_every_s=self.uniform_every_s,
        )

        t0 = time.monotonic()
        extracted: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        cancelled = False
        for kf in keyframes:
            if cancel_token is not None and getattr(cancel_token, "cancelled", False):
                cancelled = True
                break
            try:
                arr = self.decoder.extract_frame(source_path, time_s=kf.time_s)
            except RuntimeError as ex:
                skipped.append({
                    "scene_idx": kf.scene_idx, "role": kf.role,
                    "time_s": kf.time_s, "reason": str(ex),
                })
                continue
            fname = f"scene{kf.scene_idx:04d}_{kf.role}_{kf.time_s:.2f}.jpg"
            target = kf_dir / fname
            Image.fromarray(arr).save(
                target, format="JPEG", quality=self.jpeg_quality,
            )
            extracted.append({
                "scene_idx": kf.scene_idx,
                "role": kf.role,
                "time_s": kf.time_s,
                "path": str(target.relative_to(storage_dir)),
            })

        # Wenn weniger als 50% extrahiert: partial. Sonst done.
        wanted = len(keyframes)
        got = len(extracted)
        if cancelled:
            status = "partial"
        elif wanted == 0:
            status = "done"
        elif got == 0:
            status = "failed"
        elif got < wanted * 0.5:
            status = "partial"
        else:
            status = "done"

        index_json = storage_dir / "keyframes.json"
        index_json.write_text(json.dumps(extracted, indent=2))

        return StageResult(
            stage_id=self.stage_id, status=status,
            duration_s=time.monotonic() - t0,
            artifacts={"keyframes_json": index_json, "keyframes_dir": kf_dir},
            metrics={
                "keyframe_count": len(extracted),
                "skipped_count": len(skipped),
                "wanted_count": wanted,
            },
            error="cancelled" if cancelled else None,
        )
