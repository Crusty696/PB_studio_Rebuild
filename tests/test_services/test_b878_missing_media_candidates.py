from __future__ import annotations

from pathlib import Path


def test_b878_video_info_revalidates_source_files_on_every_call(
    monkeypatch, tmp_path: Path
):
    from services import pacing_beat_grid as pbg

    valid = tmp_path / "valid.mp4"
    valid.write_bytes(b"video")
    missing = tmp_path / "missing.mp4"
    cached_info = {
        1: {"duration": 10.0, "path": str(valid), "scenes": []},
        2: {"duration": 10.0, "path": str(missing), "scenes": []},
    }

    monkeypatch.setattr(pbg, "_engine_cache_identity", lambda: (1, "test"))
    monkeypatch.setattr(pbg, "_get_video_info_cached", lambda *_: cached_info)

    assert set(pbg._get_video_info([1, 2])) == {1}

    valid.unlink()
    assert pbg._get_video_info([1, 2]) == {}
