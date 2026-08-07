"""B-397 (migriert per B-769 / Consulting-Review 2026-08-07).

Schutzzweck B-397 (unveraendert): NIE ein kaputtes Video mit stillen
Sprungstellen rendern — an ffmpeg darf keine Segmentliste mit Luecken gehen.

Verhalten (geaendert per B-769, entschieden durch Hauptagent nach
Consulting-Review 2026-08-07): Statt bei einer Luecke zwischen UNLOCKED
Segmenten den GESAMTEN Export mit ValueError abzubrechen, heilt
export_timeline die Luecke IN-MEMORY auf der geladenen Segmentliste
(heal_video_timeline_gaps, Nachruecken) — die DB bleibt dabei byte-identisch
(kein stiller Write am QUndoStack vorbei). Der B-397-Schutz lebt in neuer
Form weiter: die an ffmpeg uebergebene Liste MUSS lueckenlos sein.

Unschliessbare Faelle (Luecke beidseitig von gelockten Segmenten, kein
Restmaterial) schlagen weiterhin hart und praezise fehl — Fehlerpfad-Test
unten plus DB-basierte Variante in
tests/test_services/test_b769_timeline_gap_invariant.py.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from tests.test_services.test_b395_export_source_range_validation import _Session


class _FfmpegReached(Exception):
    """Sentinel: concat-Pfad wurde mit der finalen Segmentliste erreicht."""

    def __init__(self, video_segments):
        super().__init__("ffmpeg reached")
        self.video_segments = video_segments


def _entry(eid, media_id, start, end, locked=False):
    return SimpleNamespace(
        id=eid,
        project_id=1,
        track="video",
        media_id=media_id,
        start_time=start,
        end_time=end,
        source_start=0.0,
        source_end=end - start,
        crossfade_duration=0.0,
        brightness=0.0,
        contrast=1.0,
        locked=locked,
    )


def _wire_export_mocks(exp, monkeypatch, tmp_path, entries, clips,
                       concat_fn=None):
    monkeypatch.setattr(exp, "_cleanup_orphan_tempfiles", lambda: 0)
    monkeypatch.setattr(exp, "clear_probe_cache", lambda: None)
    monkeypatch.setattr(exp, "_get_export_dir", lambda: tmp_path / "exports")
    monkeypatch.setattr(exp, "Session", lambda engine: _Session(entries, clips))
    if concat_fn is None:
        def concat_fn(video_segments, *args, **kwargs):
            raise _FfmpegReached(video_segments)
    monkeypatch.setattr(exp, "_export_optimized_concat", concat_fn)


def test_b397_export_heals_gap_and_hands_gapless_segments_to_ffmpeg(
    tmp_path, monkeypatch, caplog,
):
    """Schliessbare 9s-Luecke (beide Segmente unlocked): kein ValueError mehr,
    Heal-Logzeile, ffmpeg erreicht, Segmentliste lueckenlos, DB unveraendert."""
    from services import export_service as exp

    entries = [
        _entry(20, 1, 0.0, 1.0),
        _entry(21, 2, 10.0, 11.0),
    ]
    entries_before = [(e.start_time, e.end_time) for e in entries]
    clips = [
        SimpleNamespace(id=1, file_path="a.mp4", duration=5.0),
        SimpleNamespace(id=2, file_path="b.mp4", duration=5.0),
    ]
    _wire_export_mocks(exp, monkeypatch, tmp_path, entries, clips)

    # KEIN ValueError mehr — Heal schliesst die Luecke in-memory, der
    # Export laeuft bis zum (gemockten) ffmpeg-Concat durch.
    with caplog.at_level(logging.INFO, logger="services.export_service"):
        with pytest.raises(_FfmpegReached) as excinfo:
            exp.export_timeline(project_id=1, output_name="safe.mp4")

    # Heal-Logzeile vorhanden (B-769-Vertrag: in-memory, DB unveraendert)
    assert any(
        "B-769" in rec.getMessage()
        and "in-memory geschlossen" in rec.getMessage()
        for rec in caplog.records
    ), "Heal-Logzeile 'B-769: ... in-memory geschlossen (DB unveraendert)' fehlt"

    # B-397-Schutzkern in neuer Form: die an ffmpeg uebergebene Segmentliste
    # ist LUECKENLOS (keine stillen Sprungstellen im gerenderten Video).
    segs = excinfo.value.video_segments
    assert len(segs) == 2
    prev_end = 0.0
    for i, seg in enumerate(segs):
        gap = float(seg["start"]) - prev_end
        assert gap <= 0.05, (
            f"Luecke {gap:.3f}s vor ffmpeg-Segment {i} — B-397-Schutz verletzt"
        )
        prev_end = max(prev_end, float(seg["end"]))

    # Kern der Review-Korrektur: die DB-Zeilen (hier: die gefakten Entries)
    # sind byte-identisch geblieben — Heilung war NUR in-memory.
    assert [(e.start_time, e.end_time) for e in entries] == entries_before


def test_b397_unclosable_gap_between_locked_still_fails_hard(
    tmp_path, monkeypatch,
):
    """Fehlerpfad bleibt hart: Luecke zwischen ZWEI gelockten Segmenten ist
    ohne Lock-Bruch nicht schliessbar -> praeziser ValueError mit
    Zeitposition, ffmpeg wird NIE erreicht."""
    from services import export_service as exp

    entries = [
        _entry(30, 1, 0.0, 5.0),
        _entry(31, 2, 5.0, 8.0, locked=True),
        # Luecke 8.0 -> 10.0 direkt zwischen zwei locked Ankern
        _entry(32, 3, 10.0, 13.0, locked=True),
    ]
    # KEIN Restmaterial: clip.duration == genutzte source-Spanne
    clips = [
        SimpleNamespace(id=1, file_path="a.mp4", duration=5.0),
        SimpleNamespace(id=2, file_path="b.mp4", duration=3.0),
        SimpleNamespace(id=3, file_path="c.mp4", duration=3.0),
    ]

    def _must_not_reach(video_segments, *args, **kwargs):
        raise AssertionError("FFmpeg path reached")

    _wire_export_mocks(
        exp, monkeypatch, tmp_path, entries, clips, concat_fn=_must_not_reach,
    )

    with pytest.raises(ValueError, match=(
        r"B-769: Timeline-Luecke 8\.000s bis 10\.000s.*gelockter Clips"
    )):
        exp.export_timeline(project_id=1, output_name="safe.mp4")
