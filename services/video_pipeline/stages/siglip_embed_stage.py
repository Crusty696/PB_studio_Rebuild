"""SigLIP-Embed-Stage (wraps SigLipEmbedService).

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 31 Stage (Tier 3)
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from services.video_pipeline.stages.base import StageResult
from services.video_pipeline.stages.siglip_embed_service import SigLipEmbedService


__all__ = ["SigLipEmbedStage"]


class SigLipEmbedStage:
    stage_id = "siglip_embed"

    def __init__(
        self,
        *,
        service: SigLipEmbedService | None = None,
        batch_size: int = 8,
    ):
        self.service = service or SigLipEmbedService()
        self.batch_size = batch_size

    def unload(self) -> None:
        """Free the SigLIP model from VRAM (F-1). Called by the orchestrator
        after the stage completes so the next GPU stage has headroom."""
        self.service.unload()

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
        if not keyframes:
            return StageResult(
                stage_id=self.stage_id, status="done", duration_s=0.0,
                metrics={"embeddings_count": 0},
            )

        t0 = time.monotonic()
        try:
            # Befund 2: gesamten GPU-Abschnitt unter den zentralen gpu_serializer
            # stellen (haelt zusaetzlich den legacy GPU_EXECUTION_LOCK). Damit kann
            # waehrend dieser Stage kein anderer GPU-Consumer (Demucs, convert-NVENC,
            # brain_v3) laufen ODER das ModelManager-Modell wegswappen.
            from services.brain_v3.gpu_serializer import get_default_serializer
            all_embeds: list[np.ndarray] = []
            with get_default_serializer().acquire("video_pipeline_siglip"):
                for i in range(0, len(keyframes), self.batch_size):
                    if cancel_token is not None and getattr(cancel_token, "cancelled", False):
                        break
                    batch = keyframes[i: i + self.batch_size]
                    imgs = []
                    for kf in batch:
                        img_path = storage_dir / kf["path"]
                        imgs.append(np.array(Image.open(img_path).convert("RGB")))
                    arr = self.service.embed_batch(imgs)
                    all_embeds.append(arr)
        except Exception as ex:
            return StageResult(
                stage_id=self.stage_id, status="failed",
                duration_s=time.monotonic() - t0, error=f"{type(ex).__name__}: {ex}",
            )

        if not all_embeds:
            return StageResult(
                stage_id=self.stage_id, status="partial",
                duration_s=time.monotonic() - t0,
                error="cancelled before any batch",
            )

        stacked = np.concatenate(all_embeds, axis=0)
        out_npy = storage_dir / "embeddings.npy"
        np.save(out_npy, stacked)

        return StageResult(
            stage_id=self.stage_id, status="done",
            duration_s=time.monotonic() - t0,
            artifacts={"embeddings_npy": out_npy},
            metrics={
                "embeddings_count": int(stacked.shape[0]),
                "embedding_dim": int(stacked.shape[1]),
                "dtype": str(stacked.dtype),
                "model_id": self.service.model_id,
            },
        )
