"""Stage-Base fuer Video-Pipeline.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phases: 30/34/35/36 (Tier 3 Workspace+Services)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


__all__ = ["StageResult", "Stage", "StageError"]


class StageError(RuntimeError):
    """Wird geworfen wenn Stage nicht aus Konfig-Fehler / Setup-Problem laufen kann."""


@dataclass
class StageResult:
    stage_id: str
    status: str                          # "done" | "partial" | "failed" | "skipped"
    duration_s: float
    artifacts: dict[str, Path] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class Stage(Protocol):
    stage_id: str

    def run(
        self,
        source_path: Path,
        storage_dir: Path,
        *,
        cancel_token: Any | None = None,
    ) -> StageResult: ...
