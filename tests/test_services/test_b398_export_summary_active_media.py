from __future__ import annotations

from types import SimpleNamespace

from tests.test_services.test_b395_export_source_range_validation import _Session


def test_b398_summary_counts_only_exportable_video_entries(monkeypatch):
    from services import export_service as exp

    entries = [
        SimpleNamespace(id=30, track="video", media_id=1, start_time=0.0, end_time=1.0),
        SimpleNamespace(id=31, track="video", media_id=2, start_time=1.0, end_time=2.0),
        SimpleNamespace(id=32, track="video", media_id=3, start_time=2.0, end_time=3.0),
    ]
    clips = [
        SimpleNamespace(id=1, deleted_at=None),
        SimpleNamespace(id=2, deleted_at="2026-05-26T00:00:00"),
    ]

    monkeypatch.setattr(exp, "Session", lambda engine: _Session(entries, clips))

    summary = exp.get_timeline_summary(project_id=1)

    assert summary["video_clips"] == 1
    assert summary["audio_tracks"] == 0
    assert summary["total_entries"] == 1
    assert summary["estimated_duration"] == 1.0

