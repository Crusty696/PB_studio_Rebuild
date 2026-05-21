from __future__ import annotations

from types import SimpleNamespace

import pytest


def test_b324_pipeline_worker_ignores_stale_proxy_when_source_exists(tmp_path):
    from workers.video import _resolve_pipeline_analysis_path

    source = tmp_path / "clip.mp4"
    source.write_bytes(b"fake")
    stale_proxy = tmp_path / "missing_proxy.mp4"
    clip = SimpleNamespace(file_path=str(source), proxy_path=str(stale_proxy))

    assert _resolve_pipeline_analysis_path(clip, 42) == str(source)


def test_b324_pipeline_worker_uses_existing_proxy(tmp_path):
    from workers.video import _resolve_pipeline_analysis_path

    source = tmp_path / "clip.mp4"
    source.write_bytes(b"fake")
    proxy = tmp_path / "clip_proxy.mp4"
    proxy.write_bytes(b"fake-proxy")
    clip = SimpleNamespace(file_path=str(source), proxy_path=str(proxy))

    assert _resolve_pipeline_analysis_path(clip, 42) == str(proxy)


def test_b324_run_full_pipeline_missing_input_is_failure(tmp_path):
    from services.video_analysis_service import run_full_pipeline

    missing = tmp_path / "missing.mp4"

    with pytest.raises(FileNotFoundError, match="Video-Datei fehlt"):
        run_full_pipeline(str(missing), video_clip_id=42)
