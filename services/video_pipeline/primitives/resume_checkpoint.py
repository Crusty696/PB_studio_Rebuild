"""Resume-Checkpoint.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 17 (Tier 2 Building-Blocks)

JSON-Datei pro Job. Atomic-Write (tmp + os.replace).
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


__all__ = ["ResumeCheckpoint", "CheckpointMismatch"]


class CheckpointMismatch(RuntimeError):
    pass


class ResumeCheckpoint:
    PLAN_ID = "VIDEO-PIPELINE-ENGINE-2026-05-19"

    def __init__(self, path: Path, *, track_id: int, stream_sha256: str):
        self.path = Path(path)
        self.track_id = track_id
        self.stream_sha256 = stream_sha256
        self.stages: dict[str, dict[str, Any]] = {}
        self.last_update: str | None = None

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        track_id: int | None = None,
        stream_sha256: str | None = None,
    ) -> "ResumeCheckpoint":
        path = Path(path)
        if not path.exists():
            return cls(
                path,
                track_id=track_id if track_id is not None else 0,
                stream_sha256=stream_sha256 or "",
            )

        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        loaded_sha = data.get("stream_sha256", "")
        if stream_sha256 is not None and loaded_sha != stream_sha256:
            raise CheckpointMismatch(
                f"checkpoint sha {loaded_sha!r} != expected {stream_sha256!r}"
            )

        cp = cls(
            path,
            track_id=data.get("track_id", track_id or 0),
            stream_sha256=loaded_sha,
        )
        cp.stages = data.get("stages", {})
        cp.last_update = data.get("last_update")
        return cp

    def update_stage(self, stage_id: str, *, status: str, **fields: Any) -> None:
        entry = {"status": status}
        entry.update(fields)
        self.stages[stage_id] = entry
        self.last_update = datetime.utcnow().isoformat()

    def completed_stages(self) -> list[str]:
        """Stages safe to skip on resume.

        B-365: a stage counts as completed only if it is ``done`` AND every
        artifact it recorded still exists on disk. If a recorded artifact is
        missing (deleted/moved/unreadable), the stage is NOT reported as done,
        so the orchestrator re-runs it instead of blindly skipping to a
        follow-up stage that expects e.g. ``scenes.json`` / ``keyframes.json``
        / ``embeddings.npy``. Stages with no recorded artifacts (legacy
        checkpoints written before B-365) keep the old status-only behaviour.
        """
        completed: list[str] = []
        for sid, s in self.stages.items():
            if s.get("status") != "done":
                continue
            artifacts = s.get("artifacts")
            if artifacts and not all(os.path.exists(p) for p in artifacts):
                continue
            completed.append(sid)
        return completed

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "plan_id": self.PLAN_ID,
            "track_id": self.track_id,
            "stream_sha256": self.stream_sha256,
            "stages": self.stages,
            "last_update": self.last_update or datetime.utcnow().isoformat(),
        }
        # Atomic write via tmp + replace
        fd, tmp_path = tempfile.mkstemp(
            prefix=self.path.name + ".",
            suffix=".tmp",
            dir=str(self.path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            os.replace(tmp_path, self.path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
            raise
