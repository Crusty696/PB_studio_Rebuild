"""B-580 — Export verwirft soft-geloeschte/fehlende VideoClips still.

In ``export_service.export_timeline`` (~Zeile 574) und
``export_service.export_preview`` (~Zeile 1544) wird ein ``TimelineEntry``
mit ``track="video"`` gegen ``VideoClip ... deleted_at.is_(None)`` gejoint.
Ist der Clip soft-geloescht (``deleted_at`` gesetzt) oder fehlt er, faellt
das Segment OHNE Log/Fehler aus dem Export — der User merkt das fehlende
Segment erst im fertigen Video (D-028: ``media_id`` ist kein FK).

Fix-Richtung (minimal): an den Skip-Stellen eine ``logger.warning`` mit
``entry_id``/``media_id`` ausgeben. Kein Abbruch des Exports — nur
Sichtbarkeit.

Test: ein gueltiger + ein "fehlender" Clip (soft-geloescht -> faellt durch
den ``deleted_at.is_(None)``-Filter, taucht also NICHT in der Clip-Liste
auf). Erwartung: WARNING mit der ``media_id`` des fehlenden Clips.
"""
from __future__ import annotations

import logging

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


def test_b580_export_timeline_warns_on_missing_clip(tmp_path, monkeypatch, caplog):
    """export_timeline: soft-geloeschter Clip -> WARNING mit media_id, kein Crash."""
    from services import export_service as exp

    good = _video_entry(id=1, media_id=1, start_time=0.0, end_time=1.0)
    # media_id=999 zeigt auf einen soft-geloeschten Clip -> nicht in clip-Liste.
    missing = _video_entry(id=2, media_id=999, start_time=1.0, end_time=2.0)
    clips = [SimpleNamespace(id=1, file_path="good.mp4", duration=1.0)]

    captured = {}

    def _fake_concat(video_segments, *args, **kwargs):
        captured["segments"] = video_segments
        return str(tmp_path / "out.mp4")

    monkeypatch.setattr(exp, "_cleanup_orphan_tempfiles", lambda: 0)
    monkeypatch.setattr(exp, "clear_probe_cache", lambda: None)
    monkeypatch.setattr(exp, "_get_export_dir", lambda: tmp_path / "exports")
    monkeypatch.setattr(exp, "Session", lambda engine: _Session([good, missing], clips))
    monkeypatch.setattr(exp, "_export_optimized_concat", _fake_concat)
    monkeypatch.setattr(exp, "_export_with_filtergraph", _fake_concat)

    with caplog.at_level(logging.WARNING, logger=exp.logger.name):
        exp.export_timeline(project_id=1, output_name="out.mp4")

    # Export laeuft weiter, gueltiges Segment ist drin.
    assert [s["path"] for s in captured["segments"]] == ["good.mp4"]

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("999" in r.getMessage() for r in warnings), (
        "B-580: fehlender/soft-geloeschter Clip (media_id=999) muss eine "
        "WARNING erzeugen, nicht still verworfen werden. "
        f"Gefundene Warnings: {[r.getMessage() for r in warnings]}"
    )


def test_b580_export_preview_warns_on_missing_clip(tmp_path, monkeypatch, caplog):
    """export_preview: soft-geloeschter Clip -> WARNING mit media_id, kein Crash."""
    from services import export_service as exp

    good = _video_entry(id=1, media_id=1, start_time=0.0, end_time=1.0)
    missing = _video_entry(id=2, media_id=888, start_time=1.0, end_time=2.0)
    clips = [SimpleNamespace(id=1, file_path="good.mp4", duration=1.0)]

    captured = {}

    def _fake_concat(video_segments, *args, **kwargs):
        captured["segments"] = video_segments
        return str(tmp_path / "preview.mp4")

    monkeypatch.setattr(exp, "_cleanup_orphan_tempfiles", lambda: 0)
    monkeypatch.setattr(exp, "clear_probe_cache", lambda: None)
    monkeypatch.setattr(exp, "_get_export_dir", lambda: tmp_path / "exports")
    monkeypatch.setattr(exp, "Session", lambda engine: _Session([good, missing], clips))
    monkeypatch.setattr(exp, "_export_optimized_concat", _fake_concat)
    monkeypatch.setattr(exp, "_export_with_filtergraph", _fake_concat)

    with caplog.at_level(logging.WARNING, logger=exp.logger.name):
        exp.export_preview(project_id=1, duration_limit=10.0)

    assert [s["path"] for s in captured["segments"]] == ["good.mp4"]

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("888" in r.getMessage() for r in warnings), (
        "B-580: fehlender/soft-geloeschter Clip (media_id=888) muss eine "
        "WARNING erzeugen, nicht still verworfen werden. "
        f"Gefundene Warnings: {[r.getMessage() for r in warnings]}"
    )
