"""Video-Pipeline-Orchestrator (plain Python, Qt-Wrapping in Tier 3 Phase 37/38).

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 30 (Tier 3 Workspace+Services)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, Sequence

from services.video_pipeline.primitives.resume_checkpoint import ResumeCheckpoint
from services.video_pipeline.stages.base import StageResult


logger = logging.getLogger(__name__)

try:
    from database import nullpool_session
except ImportError:
    nullpool_session = None

__all__ = ["VideoAnalysisPipeline", "PipelineListener", "CancelToken", "PipelineResult"]


@dataclass
class CancelToken:
    cancelled: bool = False

    def cancel(self) -> None:
        self.cancelled = True


class PipelineListener(Protocol):
    def on_stage_started(self, track_id: int, stage_id: str) -> None: ...
    def on_stage_done(self, track_id: int, result: StageResult) -> None: ...
    def on_stage_failed(self, track_id: int, result: StageResult) -> None: ...
    def on_pipeline_done(self, track_id: int) -> None: ...


@dataclass
class PipelineResult:
    track_id: int
    stage_results: list[StageResult] = field(default_factory=list)
    cancelled: bool = False
    completed_count: int = 0
    failed_count: int = 0


class _NullListener:
    def on_stage_started(self, *a, **k): pass
    def on_stage_done(self, *a, **k): pass
    def on_stage_failed(self, *a, **k): pass
    def on_pipeline_done(self, *a, **k): pass


class VideoAnalysisPipeline:
    """Sequentieller Orchestrator. Fuehrt Stages topologisch aus.

    - Respektiert ``checkpoint.completed_stages()`` -> skip done.
    - Cancel-Token wird vor jeder Stage + an Stages weitergegeben.
    - Listener bekommt Events (UI-Phase wired das auf Qt-Signals).
    """

    def __init__(
        self,
        *,
        track_id: int,
        source_path: Path,
        storage_dir: Path,
        stages: Sequence,
        checkpoint: ResumeCheckpoint | None = None,
        listener: PipelineListener | None = None,
    ):
        self.track_id = track_id
        self.source_path = Path(source_path)
        self.storage_dir = Path(storage_dir)
        self.stages = list(stages)
        self.checkpoint = checkpoint
        self.listener = listener or _NullListener()
        self.cancel_token = CancelToken()

    def cancel(self) -> None:
        self.cancel_token.cancel()

    def run(self) -> PipelineResult:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        result = PipelineResult(track_id=self.track_id)

        done_stages = (
            set(self.checkpoint.completed_stages()) if self.checkpoint else set()
        )

        for stage in self.stages:
            if self.cancel_token.cancelled:
                result.cancelled = True
                break

            sid = stage.stage_id
            if sid in done_stages:
                # Skip already-done stage; emit "skipped" event
                skipped = StageResult(
                    stage_id=sid, status="skipped",
                    duration_s=0.0,
                    metrics={"reason": "checkpoint_done"},
                )
                result.stage_results.append(skipped)
                self.listener.on_stage_done(self.track_id, skipped)
                continue

            self.listener.on_stage_started(self.track_id, sid)
            try:
                sr = stage.run(
                    self.source_path, self.storage_dir,
                    cancel_token=self.cancel_token,
                )
            except Exception as ex:
                # F-19 (B-351): keep the short error string for the StageResult,
                # but log the full traceback so a stage crash (e.g. CUDA OOM) is
                # not reduced to a one-line message with no stack.
                logger.exception("stage %s crashed", sid)
                sr = StageResult(
                    stage_id=sid, status="failed",
                    duration_s=0.0, error=f"{type(ex).__name__}: {ex}",
                )

            result.stage_results.append(sr)

            stop_after_stage = self.cancel_token.cancelled
            if stop_after_stage and sr.status == "done":
                sr.status = "partial"
                sr.error = sr.error or "cancelled"

            try:
                if sr.status == "done":
                    result.completed_count += 1
                    self._record_stage_provenance(sr)
                    self.listener.on_stage_done(self.track_id, sr)
                elif sr.status == "failed":
                    result.failed_count += 1
                    self.listener.on_stage_failed(self.track_id, sr)
                else:
                    # partial / skipped
                    self.listener.on_stage_done(self.track_id, sr)

                if self.checkpoint is not None:
                    # B-365: persist artifact paths so a later resume can verify
                    # they still exist before blindly skipping the done stage.
                    self.checkpoint.update_stage(
                        sid, status=sr.status,
                        duration_s=sr.duration_s,
                        error=sr.error,
                        artifacts=[str(p) for p in sr.artifacts.values()],
                    )
                    self.checkpoint.save()
            finally:
                # F-1/B-364: release any GPU model the stage holds even if
                # listener callbacks or checkpoint persistence fail.
                _unload = getattr(stage, "unload", None)
                if callable(_unload):
                    try:
                        _unload()
                    except Exception:
                        logger.exception("stage %s unload failed", sid)

            if stop_after_stage:
                result.cancelled = True
                break

        self.listener.on_pipeline_done(self.track_id)
        return result

    def _record_stage_provenance(self, stage_result: StageResult) -> None:
        """OTK-021/40: Plan-A video stages write analysis_jobs/artifacts."""
        if nullpool_session is None or not stage_result.artifacts:
            return
        try:
            from database import VideoClip
            from services.storage_provenance.caller_migration import ProvenanceRecorder
        except ImportError:
            return
        try:
            with nullpool_session() as sess:
                clip = sess.query(VideoClip).filter(VideoClip.id == self.track_id).first()
                if clip is None or not getattr(clip, "project_id", None):
                    return
                source_path = getattr(clip, "file_path", None) or self.source_path
                if not source_path:
                    return
                ProvenanceRecorder(sess).record_done(
                    project_id=clip.project_id,
                    source_path=source_path,
                    media_type="video",
                    step_id=f"video.{stage_result.stage_id}",
                    params={"stage": stage_result.stage_id},
                    artifacts=dict(stage_result.artifacts),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Video provenance track=%s stage=%s fehlgeschlagen: %s",
                self.track_id,
                stage_result.stage_id,
                exc,
            )
