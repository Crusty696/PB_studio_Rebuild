"""Cycle 4 LOW batch2 regression tests.

Bundles 6 LOW-severity structural fixes:

* B-151 + B-155: ingest_audio/ingest_video gain ``invalidate_caches``
  flag; FolderImportWorker uses ``invalidate_caches=False`` per file
  and calls ``_invalidate_pacing_caches()`` once at end-of-batch.
* B-152: BeatAnalysisService chunk-overlap dedup uses final-pass
  ``np.unique(np.round(beats, 2))`` instead of fragile running-state
  monotonic dedup.
* B-153: delete_selected_media uses conditional ``or_(*conds)`` build
  instead of ``IN ([0])`` sentinel that could match a real ``id=0``
  row.
* B-154: SigLIP OOM-retry inner loop runs ``torch.cuda.empty_cache()``
  BEFORE each per-sample processor() call so OOM doesn't cascade.
* B-156: VideoAnalyzer.create_proxy holds a per-proxy-path
  ``threading.Lock`` around unlink + ffmpeg-rewrite so concurrent
  pipeline workers don't see a deleted file.
"""

from __future__ import annotations

import inspect

from services import beat_analysis_service, ingest_service, video_analysis_service, video_service
from workers import import_export as workers_import_export


def test_b151_ingest_audio_video_have_invalidate_caches_flag() -> None:
    """B-151: ingest_audio/ingest_video must accept invalidate_caches
    keyword arg and only call _invalidate_pacing_caches when True."""
    sig_audio = inspect.signature(ingest_service.ingest_audio)
    sig_video = inspect.signature(ingest_service.ingest_video)
    assert "invalidate_caches" in sig_audio.parameters, (
        "B-151 regression: ingest_audio missing invalidate_caches kwarg."
    )
    assert "invalidate_caches" in sig_video.parameters, (
        "B-151 regression: ingest_video missing invalidate_caches kwarg."
    )
    src = inspect.getsource(ingest_service)
    assert "if invalidate_caches:" in src, (
        "B-151 regression: invalidate_caches flag is no longer "
        "guarding _invalidate_pacing_caches calls."
    )


def test_b155_folder_import_worker_uses_batch_invalidate() -> None:
    """B-155: FolderImportWorker must call ingest_*(invalidate_caches=
    False) inside the loop and _invalidate_pacing_caches() once after
    the loop."""
    src = inspect.getsource(workers_import_export)
    assert "ingest_audio(p, invalidate_caches=False)" in src, (
        "B-155 regression: FolderImportWorker no longer suppresses "
        "per-file pacing-cache invalidate for audio — N+1 storm back."
    )
    assert "ingest_video(p, invalidate_caches=False)" in src, (
        "B-155 regression: FolderImportWorker no longer suppresses "
        "per-file pacing-cache invalidate for video."
    )
    assert "_invalidate_pacing_caches" in src, (
        "B-155 regression: FolderImportWorker no longer calls "
        "_invalidate_pacing_caches() once at end-of-batch."
    )


def test_b152_beat_analysis_uses_final_pass_dedup() -> None:
    """B-152: chunked path must run final-pass np.unique/np.round on
    accumulated beats instead of relying on running-state dedup which
    fails at chunk boundaries."""
    src = inspect.getsource(beat_analysis_service)
    assert "np.unique(np.round" in src, (
        "B-152 regression: chunked beat dedup no longer uses "
        "np.unique(np.round(...)) — fragile monotonic-only dedup back."
    )


def test_b153_no_zero_sentinel_in_delete_selected_media() -> None:
    """B-153: ``IN ([0])`` sentinel is replaced by conditional
    or_-build."""
    src = inspect.getsource(ingest_service)
    bad_pattern_a = "audio_ids if audio_ids else [0]"
    bad_pattern_b = "video_ids if video_ids else [0]"
    assert bad_pattern_a not in src, (
        "B-153 regression: ``IN ([0])`` audio sentinel still present "
        "— a real row with id=0 will be falsely matched."
    )
    assert bad_pattern_b not in src, (
        "B-153 regression: ``IN ([0])`` video sentinel still present."
    )
    assert "or_(*anchor_conds)" in src or "or_(*conds)" in src, (
        "B-153 regression: conditional or_-build for AudioVideoAnchor "
        "delete is gone."
    )


def test_b154_siglip_oom_retry_calls_empty_cache_per_sample() -> None:
    """B-154: SigLIP OOM-retry inner loop must call
    torch.cuda.empty_cache() BEFORE each processor() call so that
    per-sample memory issues don't cascade."""
    src = inspect.getsource(video_analysis_service)
    # Heuristic: find the per-sample retry block (`for j, (img, scene)
    # in enumerate(zip(images, valid_scenes))`) and check the next 12
    # lines mention empty_cache before processor.
    lines = src.splitlines()
    found_block = False
    block_calls_empty_cache_first = False
    for i, line in enumerate(lines):
        if "for j, (img, scene) in enumerate" not in line:
            continue
        found_block = True
        window = lines[i:i + 15]
        # Find the offset of empty_cache and processor( within window.
        ec_idx = next(
            (k for k, w in enumerate(window) if "torch.cuda.empty_cache()" in w),
            None,
        )
        proc_idx = next(
            (k for k, w in enumerate(window) if "processor(images=" in w),
            None,
        )
        if ec_idx is not None and proc_idx is not None and ec_idx < proc_idx:
            block_calls_empty_cache_first = True
        break
    assert found_block, (
        "B-154 inspection target moved — per-sample OOM-retry block "
        "no longer matches expected pattern."
    )
    assert block_calls_empty_cache_first, (
        "B-154 regression: per-sample OOM-retry doesn't call "
        "torch.cuda.empty_cache() BEFORE processor() — OOM will "
        "cascade across iterations again."
    )


def test_b156_create_proxy_uses_per_path_lock() -> None:
    """B-156: VideoAnalyzer.create_proxy must hold a per-proxy-path
    threading.Lock around unlink + ffmpeg-rewrite."""
    src = inspect.getsource(video_service)
    assert "_proxy_locks" in src, (
        "B-156 regression: per-proxy-path lock dict no longer present."
    )
    assert "_get_proxy_lock" in src, (
        "B-156 regression: proxy-lock helper function gone."
    )
    create_proxy_src = inspect.getsource(video_service.VideoAnalyzer.create_proxy)
    assert "with proxy_lock" in create_proxy_src or "with _get_proxy_lock" in create_proxy_src, (
        "B-156 regression: create_proxy no longer wraps unlink + "
        "ffmpeg-rewrite in a per-path lock — TOCTOU back."
    )
