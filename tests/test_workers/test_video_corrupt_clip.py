"""Bug A + Bug B regression tests.

Crash chain reproduced:
  corrupt MP4 (no moov atom)
    → scenedetect.video_stream.VideoOpenFailure leaks out of detect_scenes
    → outer except in VideoAnalysisPipelineWorker.run sets _errored, emits error
    → finally still emitted finished
    → Main-Thread thread.quit() fires while error-slot still processing
    → "QThread: Destroyed while thread is still running" → 0xC0000409.

Fixes:
  Bug B: services/video_analysis_service.detect_scenes wraps VideoOpenFailure
         as RuntimeError → caught by C-04 per-clip skip block.
  Bug A: VideoAnalysisPipelineWorker tracks _emitted_terminal and only emits
         finished in finally if neither error nor finished has been emitted yet.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest

# Offscreen QPA before any Qt import (matches tests/ui/test_feedback_shortcuts.py).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Module-scoped QApplication so signal connections work in tests."""
    app = QApplication.instance() or QApplication(sys.argv)
    return app  # type: ignore[return-value]


def _write_corrupt_mp4(path: Path) -> None:
    """Write a truncated MP4: ftyp box only, no moov, no mdat.

    OpenCV/ffmpeg/scenedetect probe will reach the ftyp marker but fail
    to find the moov atom → VideoOpenFailure.
    """
    path.write_bytes(
        b"\x00\x00\x00\x18ftypisom"      # ftyp box header (size=24, type=ftyp)
        b"\x00\x00\x00\x00"              # major brand version
        b"isomiso2avc1mp41"              # compatible brands (16 bytes)
        # No moov box, no mdat → ffmpeg: "moov atom not found" → VideoOpenFailure
    )


# ---------------------------------------------------------------------------
# Bug B — detect_scenes wraps VideoOpenFailure as RuntimeError
# ---------------------------------------------------------------------------

def test_detect_scenes_wraps_video_open_failure_as_runtime_error(tmp_path: Path) -> None:
    from services.video_analysis_service import detect_scenes

    corrupt = tmp_path / "broken.mp4"
    _write_corrupt_mp4(corrupt)

    with pytest.raises(RuntimeError, match=r"beschädigt|nicht lesbar"):
        detect_scenes(str(corrupt))


def test_detect_scenes_runtime_error_carries_filename(tmp_path: Path) -> None:
    from services.video_analysis_service import detect_scenes

    corrupt = tmp_path / "Clip_42_corrupt.mp4"
    _write_corrupt_mp4(corrupt)

    with pytest.raises(RuntimeError) as exc_info:
        detect_scenes(str(corrupt))

    assert "Clip_42_corrupt.mp4" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Bug A — Worker skip + signal race
# ---------------------------------------------------------------------------

def _patch_worker_run_full_pipeline(monkeypatch: pytest.MonkeyPatch, side_effect: Any) -> None:
    """Stub services.video_analysis_service.run_full_pipeline.

    The worker imports run_full_pipeline lazily inside run(), so we have to
    patch it on the source module — the lazy import then resolves to our stub.
    """
    import services.video_analysis_service as vas_mod
    monkeypatch.setattr(vas_mod, "run_full_pipeline", side_effect, raising=False)


def _patch_db_resolution(monkeypatch: pytest.MonkeyPatch, batch: list) -> None:
    """Skip the (clip_id, title) → DB lookup in run() by passing 3-tuples directly.

    The worker only resolves via DB when batch tuples have len()==2; if we feed
    3-tuples (clip_id, video_path, title), DB resolution is skipped.
    """
    # Nothing to patch — caller just needs to use 3-tuples.
    _ = batch


def _stub_gpu_locks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace ModelManager + GPU locks with no-op contexts so we don't touch CUDA."""
    import contextlib
    import services.model_manager as mm_mod

    @contextlib.contextmanager
    def _noop_lock():
        yield

    # Both locks are used as `with GPU_xxx_LOCK:` — replace with no-op contextmanager objs.
    class _NoOpLock:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    monkeypatch.setattr(mm_mod, "GPU_LOAD_LOCK", _NoOpLock(), raising=False)
    monkeypatch.setattr(mm_mod, "GPU_EXECUTION_LOCK", _NoOpLock(), raising=False)


def test_pipeline_worker_skips_corrupt_clip_and_continues(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """3-clip batch where clip 2 raises RuntimeError (corrupt-MP4 path).

    Expected: worker continues past clip 2, emits finished exactly once,
    error never emitted (per-clip RuntimeError is C-04 skip path).
    """
    from services.video_analysis_service import PipelineResult
    from workers.video import VideoAnalysisPipelineWorker

    _stub_gpu_locks(monkeypatch)

    def fake_pipeline(*, video_path: str, video_clip_id: int, **_kw: Any) -> PipelineResult:
        if video_clip_id == 2:
            raise RuntimeError(
                f"Video '{Path(video_path).name}' ist beschädigt oder nicht lesbar (test)"
            )
        return PipelineResult(video_path=video_path, scenes=[], embeddings_stored=0)

    _patch_worker_run_full_pipeline(monkeypatch, fake_pipeline)

    batch = [
        (1, str(tmp_path / "clip1.mp4"), "Clip 1"),
        (2, str(tmp_path / "clip2.mp4"), "Clip 2"),
        (3, str(tmp_path / "clip3.mp4"), "Clip 3"),
    ]
    worker = VideoAnalysisPipelineWorker(batch=batch)

    finished_calls: list[tuple] = []
    error_calls: list[tuple] = []
    progress_msgs: list[str] = []
    worker.finished.connect(lambda cid, d: finished_calls.append((cid, d)))
    worker.error.connect(lambda cid, msg: error_calls.append((cid, msg)))
    worker.progress.connect(lambda pct, msg: progress_msgs.append(msg))

    worker.run()

    assert worker._errored is False, "per-clip failure must NOT mark worker as errored"
    assert error_calls == [], f"error should NOT have been emitted, got {error_calls}"
    assert len(finished_calls) == 1, f"finished must fire exactly once, got {len(finished_calls)}"

    # The C-04 skip path emits a 'FEHLER:' progress for clip 2.
    fehler_msgs = [m for m in progress_msgs if "FEHLER" in m]
    assert any("2/3" in m for m in fehler_msgs), (
        f"expected FEHLER progress for clip 2/3, got {fehler_msgs}"
    )


def test_pipeline_worker_does_not_emit_both_error_and_finished(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If an UNEXPECTED exception propagates out (MemoryError — not in C-04 catch list),
    the outer except fires error.emit. The finally must NOT then emit finished too.
    """
    from workers.video import VideoAnalysisPipelineWorker

    _stub_gpu_locks(monkeypatch)

    def fake_pipeline(**_kw: Any):
        # MemoryError is NOT in the C-04 catch tuple (RuntimeError, OSError, ValueError)
        # → propagates to the outer except.
        raise MemoryError("simulated OOM")

    _patch_worker_run_full_pipeline(monkeypatch, fake_pipeline)

    batch = [(1, str(tmp_path / "clip1.mp4"), "Clip 1")]
    worker = VideoAnalysisPipelineWorker(batch=batch)

    finished_count = [0]
    error_count = [0]
    worker.finished.connect(lambda *_: finished_count.__setitem__(0, finished_count[0] + 1))
    worker.error.connect(lambda *_: error_count.__setitem__(0, error_count[0] + 1))

    worker.run()

    total = finished_count[0] + error_count[0]
    assert total == 1, (
        f"exactly ONE terminal signal must fire (got finished={finished_count[0]}, "
        f"error={error_count[0]})"
    )
    # Specifically: the unexpected-exception path must emit error, not finished.
    assert error_count[0] == 1
    assert finished_count[0] == 0
    assert worker._errored is True


def test_corrupt_mp4_through_pipeline_does_not_crash(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end-ish: 1-clip batch, clip is corrupt MP4. The wrap → C-04 skip
    → final finished.emit fires normally. No exception escapes worker.run()."""
    from workers.video import VideoAnalysisPipelineWorker

    _stub_gpu_locks(monkeypatch)

    corrupt = tmp_path / "broken.mp4"
    _write_corrupt_mp4(corrupt)

    # Use the REAL run_full_pipeline so detect_scenes' VideoOpenFailure-wrap is exercised.
    # This validates the full Bug-B chain: VideoOpenFailure → RuntimeError → C-04 skip.

    batch = [(99, str(corrupt), "broken")]
    worker = VideoAnalysisPipelineWorker(batch=batch)

    finished_calls: list[tuple] = []
    error_calls: list[tuple] = []
    progress_msgs: list[str] = []
    worker.finished.connect(lambda cid, d: finished_calls.append((cid, d)))
    worker.error.connect(lambda cid, msg: error_calls.append((cid, msg)))
    worker.progress.connect(lambda pct, msg: progress_msgs.append(msg))

    # Should NOT raise.
    worker.run()

    assert error_calls == [], f"corrupt-MP4 path must skip, not error: {error_calls}"
    assert len(finished_calls) == 1
    assert worker._errored is False
    fehler_msgs = [m for m in progress_msgs if "FEHLER" in m]
    assert fehler_msgs, "expected at least one 'FEHLER:' progress message for the broken clip"
    # The error message should mention the basename (Bug B contract).
    assert any("broken.mp4" in m or "beschädigt" in m or "nicht lesbar" in m for m in fehler_msgs)
