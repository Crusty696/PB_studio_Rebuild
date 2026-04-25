"""Cycle 4 LOW batch1 regression tests.

Bundles 4 LOW-severity structural fixes from Cycle 4:

* B-141: BeatAnalysisService is a singleton — device-arg after first
  __init__ silently ignored. Must warn when caller passes mismatching
  device after init.
* B-144: AnalysisWorker only caught (ValueError, RuntimeError, OSError)
  in BPM detection. SQLAlchemyError from retry-exhausted DB writes
  bypassed mark_error and left status='running' forever.
* B-146: video_analysis_service.ai_scene_caption swallowed
  OllamaPausedError into the generic ``except Exception`` and treated
  pause-during-VRAM-load as caption-failure. Need explicit early
  branch to re-raise/skip cleanly.
* B-149: workers/video.py emitted ``videos_processed = idx if
  should_stop() else total_videos`` — when cancel hit BEFORE first
  loop iteration, idx=0 was emitted while downstream UI did
  ``progress / videos_processed`` (div-by-zero). Must use a dedicated
  counter incremented only after successful processing.
"""

from __future__ import annotations

import inspect

from services import beat_analysis_service, video_analysis_service
from workers import analysis as workers_analysis
from workers import video as workers_video


def test_b141_beat_analysis_warns_on_device_change_after_init() -> None:
    """B-141: BeatAnalysisService.__init__ must warn / handle mismatch
    when caller passes a device that differs from the already-bound
    self._device on the singleton."""
    src = inspect.getsource(beat_analysis_service.BeatAnalysisService.__init__)
    assert "_initialized" in src, (
        "Singleton guard '_initialized' missing — fix may have been "
        "reverted."
    )
    # The fix must compare device against self._device when already
    # initialized and emit a warning (or raise/log) rather than silently
    # ignoring the new device.
    assert "device != self._device" in src or "device != self.device" in src, (
        "B-141 regression: BeatAnalysisService.__init__ no longer "
        "compares passed device against bound device on re-init."
    )
    assert "warning" in src.lower() or "warn" in src.lower(), (
        "B-141 regression: device-mismatch path missing warning log "
        "— silent device override re-introduced."
    )


def test_b144_analysis_worker_catches_broad_exception_for_mark_error() -> None:
    """B-144: AnalysisWorker BPM-detection retry-loop must catch broad
    Exception (not just ValueError/RuntimeError/OSError) so that
    SQLAlchemyError from retry-exhausted DB writes still calls
    mark_error and frees the row from 'running'."""
    src = inspect.getsource(workers_analysis)
    # Locate the bpm/analysis block — it must mark_error on broad
    # exception. Heuristic: find ``except Exception`` near
    # ``mark_error`` for bpm_detection.
    assert "except Exception" in src, (
        "B-144 regression: workers/analysis.py no longer catches "
        "broad Exception — SQLAlchemyError will bypass mark_error."
    )
    # And specifically: there must be a mark_error call somewhere in
    # the worker so the row state machine completes.
    assert "mark_error" in src, (
        "B-144 regression: AnalysisWorker no longer calls mark_error "
        "on failure — analysis_status row stays 'running' forever."
    )


def test_b146_video_analysis_explicit_ollama_paused_branch() -> None:
    """B-146: ai_scene_caption must catch OllamaPausedError BEFORE the
    generic ``except Exception`` so that pause-during-VRAM-load is not
    misreported as caption-failure."""
    src = inspect.getsource(video_analysis_service)
    assert "OllamaPausedError" in src, (
        "B-146 regression: OllamaPausedError no longer imported / "
        "referenced in video_analysis_service."
    )
    # Find the explicit ``except OllamaPausedError:`` clause and
    # verify it comes BEFORE any generic ``except Exception:`` in
    # the same caption-loop region. Crude proxy: the file mentions
    # the explicit clause at all.
    assert "except OllamaPausedError" in src, (
        "B-146 regression: ai_scene_caption no longer has explicit "
        "``except OllamaPausedError`` — pause exception falls through "
        "into generic Exception handler again."
    )


def test_b149_video_worker_uses_dedicated_videos_processed_counter() -> None:
    """B-149: workers/video.py finished.emit payload must use a
    dedicated counter (videos_processed += 1 after successful
    pipeline call), not ``idx if should_stop() else total_videos``."""
    src = inspect.getsource(workers_video)
    # The buggy expression must be gone from the emit payload.
    bad_expr = "idx if self.should_stop() else total_videos"
    assert bad_expr not in src, (
        "B-149 regression: workers/video.py still emits "
        "``idx if should_stop() else total_videos`` — cancel before "
        "first iteration emits 0, downstream div-by-zero."
    )
    # And the dedicated counter must exist.
    assert "videos_processed = 0" in src, (
        "B-149 regression: dedicated ``videos_processed`` counter "
        "no longer initialized in worker."
    )
    assert "videos_processed += 1" in src, (
        "B-149 regression: ``videos_processed`` counter no longer "
        "incremented per successful video — emit will always be 0."
    )
    # And it must appear in the finished.emit payload.
    assert '"videos_processed": videos_processed' in src, (
        "B-149 regression: finished.emit no longer references the "
        "dedicated videos_processed counter."
    )
