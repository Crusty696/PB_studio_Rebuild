from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.test_services.test_b395_export_source_range_validation import _Session


def test_b397_export_rejects_video_timeline_gap_before_ffmpeg(tmp_path, monkeypatch):
    from services import export_service as exp

    entries = [
        SimpleNamespace(
            id=20,
            project_id=1,
            track="video",
            media_id=1,
            start_time=0.0,
            end_time=1.0,
            source_start=0.0,
            source_end=1.0,
            crossfade_duration=0.0,
            brightness=0.0,
            contrast=1.0,
        ),
        SimpleNamespace(
            id=21,
            project_id=1,
            track="video",
            media_id=2,
            start_time=10.0,
            end_time=11.0,
            source_start=0.0,
            source_end=1.0,
            crossfade_duration=0.0,
            brightness=0.0,
            contrast=1.0,
        ),
    ]
    clips = [
        SimpleNamespace(id=1, file_path="a.mp4", duration=5.0),
        SimpleNamespace(id=2, file_path="b.mp4", duration=5.0),
    ]

    monkeypatch.setattr(exp, "_cleanup_orphan_tempfiles", lambda: 0)
    monkeypatch.setattr(exp, "clear_probe_cache", lambda: None)
    monkeypatch.setattr(exp, "_get_export_dir", lambda: tmp_path / "exports")
    monkeypatch.setattr(exp, "Session", lambda engine: _Session(entries, clips))
    monkeypatch.setattr(
        exp,
        "_export_optimized_concat",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("FFmpeg path reached")),
    )

    with pytest.raises(ValueError, match="Timeline gap"):
        exp.export_timeline(project_id=1, output_name="safe.mp4")

