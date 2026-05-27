"""B-332 — Export Quick-Preview fails before first video.

Das Preview-Fenster war fix [0, duration_limit] in Timeline-Koordinaten.
Wenn der erste Video-Clip erst NACH duration_limit beginnt (reales Projekt:
erster Clip bei 10.322s, Limit 10.0s), blieb ``video_segments`` leer und
``export_preview`` crashte mit ``ValueError: Keine Video-Clips auf der
Timeline`` — obwohl die Timeline Video-Clips hat.

Fix: das Preview-Fenster am ersten Video-Clip verankern
(``[window_start, window_start + duration_limit]``).
"""
from __future__ import annotations

from types import SimpleNamespace

from tests.test_services.test_b395_export_source_range_validation import _Session


def _video_entry(**kwargs):
    base = dict(
        id=1,
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
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_b332_preview_window_anchors_to_first_video_after_limit(tmp_path, monkeypatch):
    """Erster Clip bei 10.322s, Limit 10.0s -> Preview darf NICHT leer sein."""
    from services import export_service as exp

    entry = _video_entry(start_time=10.322, end_time=12.322, media_id=5)
    clip = SimpleNamespace(id=5, file_path="late.mp4", duration=2.0)

    captured = {}

    def _fake_concat(video_segments, *args, **kwargs):
        captured["segments"] = video_segments
        return str(tmp_path / "preview.mp4")

    monkeypatch.setattr(exp, "_cleanup_orphan_tempfiles", lambda: 0)
    monkeypatch.setattr(exp, "clear_probe_cache", lambda: None)
    monkeypatch.setattr(exp, "_get_export_dir", lambda: tmp_path / "exports")
    monkeypatch.setattr(exp, "Session", lambda engine: _Session([entry], [clip]))
    monkeypatch.setattr(exp, "_export_optimized_concat", _fake_concat)
    monkeypatch.setattr(exp, "_export_with_filtergraph", _fake_concat)

    result = exp.export_preview(project_id=1, duration_limit=10.0)

    assert result == str(tmp_path / "preview.mp4")
    assert captured["segments"], (
        "B-332: Preview-Fenster muss am ersten Video-Clip verankert sein, "
        "nicht fix [0, 10] — sonst bleibt video_segments leer."
    )
    assert captured["segments"][0]["path"] == "late.mp4"


def test_b332_preview_window_still_trims_at_window_end(tmp_path, monkeypatch):
    """Ein langer erster Clip wird am Fensterende (start + limit) beschnitten."""
    from services import export_service as exp

    # Erster Clip startet bei 10.0, dauert 30s -> Fenster [10, 20], end_time=20.
    entry = _video_entry(start_time=10.0, end_time=40.0, media_id=6)
    clip = SimpleNamespace(id=6, file_path="long.mp4", duration=30.0)

    captured = {}

    def _fake_concat(video_segments, *args, **kwargs):
        captured["segments"] = video_segments
        return str(tmp_path / "preview.mp4")

    monkeypatch.setattr(exp, "_cleanup_orphan_tempfiles", lambda: 0)
    monkeypatch.setattr(exp, "clear_probe_cache", lambda: None)
    monkeypatch.setattr(exp, "_get_export_dir", lambda: tmp_path / "exports")
    monkeypatch.setattr(exp, "Session", lambda engine: _Session([entry], [clip]))
    monkeypatch.setattr(exp, "_export_optimized_concat", _fake_concat)
    monkeypatch.setattr(exp, "_export_with_filtergraph", _fake_concat)

    exp.export_preview(project_id=1, duration_limit=10.0)

    seg = captured["segments"][0]
    assert seg["end"] == 20.0, "Fensterende = window_start(10) + limit(10) = 20"


def test_b332_preview_skips_entries_after_window(tmp_path, monkeypatch):
    """Ein zweiter Clip jenseits des Fensters wird ausgelassen."""
    from services import export_service as exp

    e1 = _video_entry(id=1, media_id=1, start_time=5.0, end_time=6.0)
    e2 = _video_entry(id=2, media_id=2, start_time=20.0, end_time=21.0)
    clips = [
        SimpleNamespace(id=1, file_path="first.mp4", duration=1.0),
        SimpleNamespace(id=2, file_path="second.mp4", duration=1.0),
    ]

    captured = {}

    def _fake_concat(video_segments, *args, **kwargs):
        captured["segments"] = video_segments
        return str(tmp_path / "preview.mp4")

    monkeypatch.setattr(exp, "_cleanup_orphan_tempfiles", lambda: 0)
    monkeypatch.setattr(exp, "clear_probe_cache", lambda: None)
    monkeypatch.setattr(exp, "_get_export_dir", lambda: tmp_path / "exports")
    monkeypatch.setattr(exp, "Session", lambda engine: _Session([e1, e2], clips))
    monkeypatch.setattr(exp, "_export_optimized_concat", _fake_concat)
    monkeypatch.setattr(exp, "_export_with_filtergraph", _fake_concat)

    # Fenster [5, 15] -> e2 (20s) draussen.
    exp.export_preview(project_id=1, duration_limit=10.0)

    paths = [s["path"] for s in captured["segments"]]
    assert paths == ["first.mp4"], (
        "B-332: Clip jenseits window_end darf nicht im Preview landen."
    )
