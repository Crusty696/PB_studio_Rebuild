"""B-397 Restluecke (2026-08-11): Timeline-Luecken werden seit B-769 fuer den
Export in-memory geheilt. Das Video wird dadurch kuerzer als die Timeline —
bisher stand das nur als INFO im Log, der User erfuhr nichts (gleiche
Silent-Failure-Klasse wie B-580/B-803).

Erwartung: die Verkuerzung wird ueber ``warning_cb`` nach oben gemeldet.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tests.test_services.test_b395_export_source_range_validation import _Session


def _ve(id, media_id, start, end):
    return SimpleNamespace(
        id=id, project_id=1, track="video", media_id=media_id,
        start_time=start, end_time=end, source_start=0.0, source_end=end - start,
        crossfade_duration=0.0, brightness=0.0, contrast=1.0,
    )


def _run_export(monkeypatch, tmp_path, entries, clips, warnings):
    from services import export_service as exp

    monkeypatch.setattr(exp, "_cleanup_orphan_tempfiles", lambda: 0)
    monkeypatch.setattr(exp, "clear_probe_cache", lambda: None)
    monkeypatch.setattr(exp, "_get_export_dir", lambda: tmp_path / "exports")
    monkeypatch.setattr(exp, "Session", lambda engine: _Session(entries, clips))

    captured = {}

    def _fake_concat(video_segments, audio_path, output_path, *a, **k):
        captured["segments"] = [dict(s) for s in video_segments]
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"x")
        return str(output_path)

    monkeypatch.setattr(exp, "_export_optimized_concat", _fake_concat)
    exp.export_timeline(
        project_id=1, output_name="gap.mp4", warning_cb=warnings.append
    )
    return captured


def test_healed_gap_is_reported_to_the_user(tmp_path, monkeypatch):
    """3s Luecke -> Export 3s kuerzer -> Warnung mit Dauer erreicht den User."""
    entries = [_ve(30, 1, 0.0, 2.0), _ve(31, 2, 5.0, 7.0)]
    clips = [
        SimpleNamespace(id=1, file_path="a.mp4", duration=10.0),
        SimpleNamespace(id=2, file_path="b.mp4", duration=10.0),
    ]
    warnings: list[str] = []

    captured = _run_export(monkeypatch, tmp_path, entries, clips, warnings)

    segs = captured["segments"]
    assert segs[1]["start"] == 2.0 and segs[1]["end"] == 4.0, (
        "Vorbedingung: B-769 heilt die Luecke in-memory"
    )
    assert warnings, "Die Verkuerzung muss den User erreichen, nicht nur das Log"
    msg = warnings[0]
    assert "3.00s" in msg, msg
    assert "kuerzer" in msg
    assert "Timeline" in msg


def test_contiguous_timeline_warns_nothing(tmp_path, monkeypatch):
    """Gegenprobe: lueckenlose Timeline -> keine Warnung (kein Fehlalarm)."""
    entries = [_ve(40, 1, 0.0, 2.0), _ve(41, 2, 2.0, 4.0)]
    clips = [
        SimpleNamespace(id=1, file_path="a.mp4", duration=10.0),
        SimpleNamespace(id=2, file_path="b.mp4", duration=10.0),
    ]
    warnings: list[str] = []

    _run_export(monkeypatch, tmp_path, entries, clips, warnings)

    assert warnings == []
