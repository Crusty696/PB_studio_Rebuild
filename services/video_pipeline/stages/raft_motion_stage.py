"""RAFT-Motion-Stage.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 32 Stage
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np

from services.video_pipeline.primitives.decoder import VideoDecoder
from services.video_pipeline.primitives.frame_sampler import sample_frame_times
from services.video_pipeline.stages.base import StageResult
from services.video_pipeline.stages.raft_motion_service import RaftMotionService


__all__ = ["RaftMotionStage"]


class RaftMotionStage:
    stage_id = "raft_motion"

    def __init__(
        self,
        *,
        service: RaftMotionService | None = None,
        decoder: VideoDecoder | None = None,
        sample_rate_s: float = 2.0,
    ):
        self.service = service or RaftMotionService(variant="raft_large")
        self.decoder = decoder or VideoDecoder()
        self.sample_rate_s = sample_rate_s

    def unload(self) -> None:
        """Free the RAFT model from VRAM (F-1)."""
        self.service.unload()

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

        t0 = time.monotonic()
        try:
            meta = self.decoder.probe(source_path)
            times = sample_frame_times(
                duration_s=meta.duration_s, fps=meta.fps,
                strategy="uniform", rate_s=self.sample_rate_s,
            )
            # Wir brauchen Frame-Paare -> aufeinanderfolgende sample-Zeiten
            pairs = list(zip(times[:-1], times[1:]))
            if not pairs:
                return StageResult(
                    stage_id=self.stage_id, status="done", duration_s=time.monotonic() - t0,
                    metrics={"pairs": 0},
                )

            motion_data: list[dict[str, Any]] = []
            for t_a, t_b in pairs:
                if cancel_token is not None and getattr(cancel_token, "cancelled", False):
                    break
                fa = self.decoder.extract_frame(source_path, t_a)
                fb = self.decoder.extract_frame(source_path, t_b)
                flow = self.service.compute_flow(fa, fb)
                stats = RaftMotionService.aggregate(flow)
                motion_data.append({
                    "time_a_s": t_a, "time_b_s": t_b,
                    "mean_magnitude": stats.mean_magnitude,
                    "std_magnitude": stats.std_magnitude,
                    "direction_rad": stats.dominant_direction_rad,
                })
        except Exception as ex:
            return StageResult(
                stage_id=self.stage_id, status="failed",
                duration_s=time.monotonic() - t0, error=f"{type(ex).__name__}: {ex}",
            )

        out_json = storage_dir / "motion.json"
        out_json.write_text(json.dumps(motion_data, indent=2))

        return StageResult(
            stage_id=self.stage_id, status="done",
            duration_s=time.monotonic() - t0,
            artifacts={"motion_json": out_json},
            metrics={"pairs": len(motion_data), "variant": self.service.variant},
        )
