"""Proxy-Gen-Stage.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 36 (Tier 3 Workspace+Services)
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from services.video_pipeline.primitives.proxy_generator import generate_proxy
from services.video_pipeline.stages.base import StageResult


__all__ = ["ProxyGenStage"]


class ProxyGenStage:
    stage_id = "proxy_gen"

    def __init__(
        self,
        *,
        max_width: int = 960,
        bitrate: str = "3M",
        codec: str = "auto",
    ):
        self.max_width = max_width
        self.bitrate = bitrate
        self.codec = codec

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
        proxy_path = storage_dir / "proxy.mp4"

        t0 = time.monotonic()
        try:
            generate_proxy(
                source_path, proxy_path,
                max_width=self.max_width,
                bitrate=self.bitrate,
                codec=self.codec,
                reuse=True,
            )
        except Exception as ex:
            return StageResult(
                stage_id=self.stage_id, status="failed",
                duration_s=time.monotonic() - t0, error=str(ex),
            )

        return StageResult(
            stage_id=self.stage_id, status="done",
            duration_s=time.monotonic() - t0,
            artifacts={"proxy_mp4": proxy_path},
            metrics={"bytes": proxy_path.stat().st_size},
        )
