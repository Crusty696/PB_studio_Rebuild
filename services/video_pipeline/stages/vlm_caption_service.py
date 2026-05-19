"""VLM-Caption-Service (Plan-B-Hook).

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 33 (Tier 3 Workspace+Services)

Standardmaessig Stub-Mode (Plan B nicht ready). Wenn ``llm_backend``
gesetzt, nutze Plan-B-Interface.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


__all__ = ["Caption", "VlmCaptionService", "LlmBackendProtocol"]


@dataclass
class Caption:
    path: Path
    text: str
    confidence: float | None = None
    model_id: str | None = None


class LlmBackendProtocol(Protocol):
    def caption_image(self, image_path: Path) -> Caption: ...


class VlmCaptionService:
    """Caption-Service mit optionalem Plan-B-Backend.

    Stub-Mode: liefert deterministische Dummy-Captions.
    Live-Mode: ruft ``llm_backend.caption_image()`` pro Frame.
    """

    def __init__(
        self,
        *,
        llm_backend: LlmBackendProtocol | None = None,
        stub_caption: str = "[VLM not wired — Plan B Phase 11 pending]",
        stub_model_id: str = "stub-vlm",
    ):
        self.llm_backend = llm_backend
        self.stub_caption = stub_caption
        self.stub_model_id = stub_model_id

    @property
    def is_stub(self) -> bool:
        return self.llm_backend is None

    def caption_keyframes(self, frame_paths: list[Path]) -> list[Caption]:
        out: list[Caption] = []
        for fp in frame_paths:
            fp = Path(fp)
            if self.llm_backend is None:
                out.append(Caption(
                    path=fp, text=self.stub_caption,
                    confidence=None, model_id=self.stub_model_id,
                ))
            else:
                out.append(self.llm_backend.caption_image(fp))
        return out
