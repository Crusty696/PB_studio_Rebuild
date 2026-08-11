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


def test_b580_warning_cb_receives_skip_with_ids(tmp_path, monkeypatch, caplog):
    """Der eigentliche Beleg: der Skip erreicht warning_cb UND das Log.

    Vertrag:
    * ``warning_cb`` wird mit Anzahl + Konsequenz gerufen (nicht nur Log).
    * Die Summen-WARNING nennt Anzahl UND die betroffenen media_ids —
      sonst muesste man sie aus den Einzelzeilen zusammensuchen.
    * Der Export laeuft weiter (kein Abbruch, B-693).
    """
    from services import export_service as exp

    good = _video_entry(id=1, media_id=1, start_time=0.0, end_time=1.0)
    gone_a = _video_entry(id=2, media_id=901, start_time=1.0, end_time=2.0)
    gone_b = _video_entry(id=3, media_id=902, start_time=2.0, end_time=3.0)
    clips = [SimpleNamespace(id=1, file_path="good.mp4", duration=1.0)]

    captured = {}
    warnings_seen: list[str] = []

    def _fake_concat(video_segments, *args, **kwargs):
        captured["segments"] = video_segments
        return str(tmp_path / "out.mp4")

    monkeypatch.setattr(exp, "_cleanup_orphan_tempfiles", lambda: 0)
    monkeypatch.setattr(exp, "clear_probe_cache", lambda: None)
    monkeypatch.setattr(exp, "_get_export_dir", lambda: tmp_path / "exports")
    monkeypatch.setattr(exp, "Session", lambda engine: _Session([good, gone_a, gone_b], clips))
    monkeypatch.setattr(exp, "_export_optimized_concat", _fake_concat)
    monkeypatch.setattr(exp, "_export_with_filtergraph", _fake_concat)

    with caplog.at_level(logging.WARNING, logger=exp.logger.name):
        exp.export_timeline(
            project_id=1,
            output_name="out.mp4",
            warning_cb=warnings_seen.append,
        )

    # Export laeuft durch, nur das gueltige Segment landet im Video.
    assert [s["path"] for s in captured["segments"]] == ["good.mp4"]

    # 1) Die Warnung erreicht den Aufrufer (UI-Kanal), nicht nur das Log.
    assert warnings_seen, (
        "B-580: uebersprungene Segmente muessen warning_cb erreichen — "
        "ein reiner Logeintrag kommt beim User nie an."
    )
    skip_msgs = [m for m in warnings_seen if "2 von 3" in m]
    assert skip_msgs, f"Anzahl fehlt in Warnung: {warnings_seen}"
    assert "901" in skip_msgs[0] and "902" in skip_msgs[0], (
        f"media_ids fehlen in Warnung: {skip_msgs[0]}"
    )

    # 2) Summen-WARNING im Log traegt Anzahl UND beide media_ids.
    summary = [
        r.getMessage() for r in caplog.records
        if r.levelno == logging.WARNING and "von 3 Video-Timeline-Eintraegen" in r.getMessage()
    ]
    assert summary, f"Summen-WARNING fehlt: {[r.getMessage() for r in caplog.records]}"
    assert "901" in summary[0] and "902" in summary[0], (
        f"Summen-WARNING ohne Clip-IDs: {summary[0]}"
    )


def test_b580_no_warning_without_skip(tmp_path, monkeypatch):
    """Kein Fehlalarm: vollstaendige Timeline -> warning_cb bleibt stumm."""
    from services import export_service as exp

    good = _video_entry(id=1, media_id=1, start_time=0.0, end_time=1.0)
    clips = [SimpleNamespace(id=1, file_path="good.mp4", duration=1.0)]
    warnings_seen: list[str] = []

    monkeypatch.setattr(exp, "_cleanup_orphan_tempfiles", lambda: 0)
    monkeypatch.setattr(exp, "clear_probe_cache", lambda: None)
    monkeypatch.setattr(exp, "_get_export_dir", lambda: tmp_path / "exports")
    monkeypatch.setattr(exp, "Session", lambda engine: _Session([good], clips))
    monkeypatch.setattr(
        exp, "_export_optimized_concat", lambda *a, **k: str(tmp_path / "out.mp4")
    )
    monkeypatch.setattr(
        exp, "_export_with_filtergraph", lambda *a, **k: str(tmp_path / "out.mp4")
    )

    exp.export_timeline(
        project_id=1, output_name="out.mp4", warning_cb=warnings_seen.append,
    )
    assert warnings_seen == []


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
