"""B-693: Ein soft-geloeschter/fehlender Clip (B-580-Skip) hinterlaesst eine
Timeline-Luecke. Frueher brach der Gap-Validator deshalb den GESAMTEN Export mit
ValueError ab (Widerspruch zur B-580-Absicht "nicht abbrechen"). Fix: die Luecke
wird geschlossen (verbleibende Segmente nach vorne gezogen), der Export laeuft
durch. Normale Exports (ohne Skip) bleiben unveraendert (Validator greift weiter).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.test_services.test_b395_export_source_range_validation import _Session


def _ve(id, media_id, start, end):
    return SimpleNamespace(
        id=id, project_id=1, track="video", media_id=media_id,
        start_time=start, end_time=end, source_start=0.0, source_end=end - start,
        crossfade_duration=0.0, brightness=0.0, contrast=1.0,
    )


def test_b693_skip_closes_gap_and_export_proceeds(tmp_path, monkeypatch):
    from services import export_service as exp

    # media_id 99 fehlt in clips -> B-580-Skip -> Luecke 2.0-4.0s.
    entries = [
        _ve(20, 1, 0.0, 2.0),
        _ve(21, 99, 2.0, 4.0),   # fehlender Clip -> uebersprungen
        _ve(22, 2, 4.0, 6.0),
    ]
    clips = [
        SimpleNamespace(id=1, file_path="a.mp4", duration=10.0),
        SimpleNamespace(id=2, file_path="b.mp4", duration=10.0),
    ]

    monkeypatch.setattr(exp, "_cleanup_orphan_tempfiles", lambda: 0)
    monkeypatch.setattr(exp, "clear_probe_cache", lambda: None)
    monkeypatch.setattr(exp, "_get_export_dir", lambda: tmp_path / "exports")
    monkeypatch.setattr(exp, "Session", lambda engine: _Session(entries, clips))

    captured = {}

    def _fake_concat(video_segments, audio_path, output_path, *a, **k):
        captured["segments"] = [dict(s) for s in video_segments]
        from pathlib import Path
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"x")
        return str(output_path)

    monkeypatch.setattr(exp, "_export_optimized_concat", _fake_concat)

    # Darf NICHT mehr mit "Timeline gap" abbrechen (B-693).
    exp.export_timeline(project_id=1, output_name="skip.mp4")

    segs = captured["segments"]
    assert len(segs) == 2, "das fehlende Segment muss uebersprungen worden sein"
    # Luecke geschlossen: Segmente lueckenlos aneinander.
    assert segs[0]["start"] == 0.0 and segs[0]["end"] == 2.0
    assert segs[1]["start"] == 2.0 and segs[1]["end"] == 4.0, (
        "Luecke nach Skip nicht geschlossen -> Export waere abgebrochen (B-693)"
    )
