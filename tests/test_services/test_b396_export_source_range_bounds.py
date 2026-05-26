from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.test_services.test_b395_export_source_range_validation import _Session


def test_b396_export_rejects_source_range_beyond_clip_duration_before_ffmpeg(tmp_path, monkeypatch):
    from services import export_service as exp

    entry = SimpleNamespace(
        id=11,
        project_id=1,
        track="video",
        media_id=8,
        start_time=0.0,
        end_time=2.0,
        source_start=100.0,
        source_end=110.0,
        crossfade_duration=0.0,
        brightness=0.0,
        contrast=1.0,
    )
    clip = SimpleNamespace(id=8, file_path="clip.mp4", duration=5.0)

    monkeypatch.setattr(exp, "_cleanup_orphan_tempfiles", lambda: 0)
    monkeypatch.setattr(exp, "clear_probe_cache", lambda: None)
    monkeypatch.setattr(exp, "_get_export_dir", lambda: tmp_path / "exports")
    monkeypatch.setattr(exp, "Session", lambda engine: _Session([entry], [clip]))
    monkeypatch.setattr(
        exp,
        "_export_optimized_concat",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("FFmpeg path reached")),
    )

    with pytest.raises(ValueError, match="clip duration"):
        exp.export_timeline(project_id=1, output_name="safe.mp4")

