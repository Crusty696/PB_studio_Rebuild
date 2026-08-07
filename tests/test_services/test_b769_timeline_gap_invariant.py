"""B-769: Repair laesst export-invalide Luecken vor LOCKED Segmenten durch.

Belegter Fall (Projekt new_test_august, 2026-08-07): repair_timeline_integrity
meldete video_gaps_closed=571, aber vor dem gelockten Entry 990 blieb eine
Luecke (3523.886s -> 3526.554s, 2.668s). Der Export brach spaeter ab mit
``ValueError: Timeline gap vor Video-Segment 990`` aus
services/export/_common.py::_validate_video_timeline_gaps.

Root Cause: Der Gap-Close-Pass in repair_timeline_integrity verschiebt NUR
unlocked Rows (``elif start > cursor + 1e-3 and not bool(row.locked)``).
Locked Rows sind Positions-Anker; das Links-Kompaktieren der unlocked Rows
OEFFNET die Luecke vor dem Anker erst bzw. laesst sie stehen. Der
Export-Validator kennt kein ``locked`` und lehnt jede Luecke > 50ms ab.

Invariante (dieser Test): Jede von repair_timeline_integrity reparierte
Video-Timeline MUSS _validate_video_timeline_gaps bestehen — locked Rows
duerfen dabei NICHT verschoben werden (Vertrag aus test_apply_auto_edit_locked).
"""
import random

import pytest
from sqlalchemy.orm import Session as DBSession

from database.models import Project, TimelineEntry, VideoClip
from services.export._common import _validate_video_timeline_gaps


def _rows_to_segments(rows):
    return [
        {"start": float(r.start_time), "end": float(r.end_time)} for r in rows
    ]


def _load_video_rows(engine, pid):
    with DBSession(engine) as s:
        return (
            s.query(TimelineEntry)
            .filter_by(project_id=pid, track="video")
            .order_by(TimelineEntry.start_time, TimelineEntry.id)
            .all()
        )


class _StopBeforeFfmpeg(Exception):
    """Sentinel: Export-Vorbereitung bis inkl. Gap-Validierung durchlaufen."""


def test_b769_export_heals_manual_gap_before_validation(test_engine, monkeypatch, tmp_path):
    """Zusatzvertrag B-769: Manuelle Timeline-Edits (Trim/Remove/Move)
    schreiben roh in die DB — kein repair-Callsite in ui/. export_timeline
    MUSS die Luecken VOR der Gap-Validierung IN-MEMORY heilen (Consulting-
    Review: Export darf die DB NICHT mutieren — kein stiller Write am
    QUndoStack vorbei), damit eine manuelle 2.7s-Luecke den Export nicht
    Minuten spaeter killt.

    Der Test laeuft NUR bis zur Validierung (kein ffmpeg): der Validator wird
    durch einen Wrapper ersetzt, der real validiert und bei Erfolg mit
    Sentinel abbricht. Vor Fix (RED): echter ValueError "Timeline gap".
    Nach Fix (GREEN): Sentinel — Luecke wurde vorher in-memory geheilt,
    die DB ist byte-identisch geblieben.
    """
    import services.export_service as es_mod
    import services.timeline_service as ts_mod
    monkeypatch.setattr(es_mod, "engine", test_engine)
    monkeypatch.setattr(ts_mod, "engine", test_engine)

    with DBSession(test_engine) as s:
        p = Project(name="b769-export-heal", path=str(tmp_path))
        s.add(p)
        s.flush()
        clip_a = VideoClip(
            project_id=p.id, file_path=str(tmp_path / "a.mp4"), duration=60.0,
        )
        clip_b = VideoClip(
            project_id=p.id, file_path=str(tmp_path / "b.mp4"), duration=60.0,
        )
        s.add_all([clip_a, clip_b])
        s.flush()
        s.add(TimelineEntry(
            project_id=p.id, track="video", media_id=clip_a.id,
            start_time=0.0, end_time=5.0, source_start=0.0, source_end=5.0,
            lane=0, locked=False,
        ))
        # Manuelle 2.7s-Luecke (z.B. nach Remove ohne Nachruecken)
        s.add(TimelineEntry(
            project_id=p.id, track="video", media_id=clip_b.id,
            start_time=7.7, end_time=12.7, source_start=0.0, source_end=5.0,
            lane=0, locked=False,
        ))
        s.commit()
        pid = p.id

    real_validator = _validate_video_timeline_gaps

    def _validate_then_stop(video_segments, *args, **kwargs):
        real_validator(video_segments, *args, **kwargs)  # wirft bei Luecke
        raise _StopBeforeFfmpeg()

    monkeypatch.setattr(
        es_mod, "_validate_video_timeline_gaps", _validate_then_stop,
    )

    # Vor Fix: ValueError "Timeline gap vor Video-Segment 2: 5.000s bis 7.700s"
    with pytest.raises(_StopBeforeFfmpeg):
        es_mod.export_timeline(project_id=pid, output_name="b769.mp4")

    # DB muss byte-identisch geblieben sein — Heilung war NUR in-memory
    # (Export darf das Projekt nicht mutieren)
    rows = _load_video_rows(test_engine, pid)
    assert rows[0].start_time == pytest.approx(0.0)
    assert rows[0].end_time == pytest.approx(5.0)
    assert rows[1].start_time == pytest.approx(7.7)
    assert rows[1].end_time == pytest.approx(12.7)


def test_b769_export_unclosable_gap_between_locked_raises_precise_error(
    test_engine, monkeypatch, tmp_path,
):
    """Pflichtvertrag locked: Luecke DIREKT zwischen zwei gelockten Segmenten
    ist ohne Lock-Bruch nicht schliessbar -> praezise Fehlermeldung mit
    Zeitposition statt rohem "Timeline gap vor Video-Segment N"."""
    import services.export_service as es_mod
    import services.timeline_service as ts_mod
    monkeypatch.setattr(es_mod, "engine", test_engine)
    monkeypatch.setattr(ts_mod, "engine", test_engine)

    with DBSession(test_engine) as s:
        p = Project(name="b769-locked-unclosable", path=str(tmp_path))
        s.add(p)
        s.flush()
        clips = [
            VideoClip(project_id=p.id, file_path=str(tmp_path / f"c{i}.mp4"),
                      duration=5.0)  # KEIN Restmaterial (source_end = duration)
            for i in range(3)
        ]
        s.add_all(clips)
        s.flush()
        s.add(TimelineEntry(
            project_id=p.id, track="video", media_id=clips[0].id,
            start_time=0.0, end_time=5.0, source_start=0.0, source_end=5.0,
            lane=0, locked=False,
        ))
        s.add(TimelineEntry(
            project_id=p.id, track="video", media_id=clips[1].id,
            start_time=5.0, end_time=8.0, source_start=0.0, source_end=3.0,
            lane=0, locked=True,
        ))
        # Luecke 8.0 -> 10.0 zwischen zwei locked Ankern
        s.add(TimelineEntry(
            project_id=p.id, track="video", media_id=clips[2].id,
            start_time=10.0, end_time=13.0, source_start=0.0, source_end=3.0,
            lane=0, locked=True,
        ))
        s.commit()
        pid = p.id

    with pytest.raises(ValueError, match=(
        r"B-769: Timeline-Luecke 8\.000s bis 10\.000s.*gelockter Clips"
    )):
        es_mod.export_timeline(project_id=pid, output_name="b769-l.mp4")


def test_b769_heal_extends_unlocked_neighbor_never_moves_locked():
    """Pflichtvertrag locked (pure function): Luecke vor gelocktem Segment
    wird durch VERLAENGERN des ungelockten Vorgaengers geschlossen; das
    gelockte Segment selbst bleibt byte-identisch."""
    from services.export._common import heal_video_timeline_gaps

    items = [
        {"start": 0.0, "end": 5.0, "locked": False,
         "source_end": 5.0, "source_duration": 5.0, "clip_duration": 60.0},
        {"start": 7.7, "end": 10.0, "locked": True,
         "source_end": 2.3, "source_duration": 2.3, "clip_duration": 60.0},
    ]
    result = heal_video_timeline_gaps(items)

    assert result["unclosable"] == []
    assert result["gaps_closed"] >= 1
    # Locked byte-identisch
    assert items[1]["start"] == 7.7 and items[1]["end"] == 10.0
    assert items[1]["source_end"] == 2.3
    # Unlocked Vorgaenger verlaengert (Restmaterial), Anschluss lueckenlos
    assert items[0]["end"] == pytest.approx(7.7)
    assert items[0]["source_end"] == pytest.approx(7.7)
    assert items[0]["source_duration"] == pytest.approx(7.7)


def test_b769_f1_overlap_island_extends_max_end_segment_not_positional():
    """F-1 (adversarialer Review 2026-08-07, Repro nachgebaut): Overlap-Insel
    [2..4] liegt POSITIONELL direkt vor dem locked Anker, aber das reale
    prev_end (10.0) kommt vom ersten Segment. Der alte Backfill verlaengerte
    die Insel (4->6), meldete gaps_closed=1 — Luecke 10->12 blieb real offen,
    Validator warf den rohen ValueError. Vertrag: das Segment mit MAXIMALEM
    end wird verlaengert, Luecke REAL geschlossen."""
    from services.export._common import heal_video_timeline_gaps

    items = [
        {"start": 0.0, "end": 10.0, "locked": False,
         "source_end": 10.0, "source_duration": 10.0, "clip_duration": 60.0},
        {"start": 2.0, "end": 4.0, "locked": False,
         "source_end": 2.0, "source_duration": 2.0, "clip_duration": 60.0},
        {"start": 12.0, "end": 14.0, "locked": True,
         "source_end": 2.0, "source_duration": 2.0, "clip_duration": 60.0},
    ]
    result = heal_video_timeline_gaps(items)

    assert result["unclosable"] == []
    # Max-End-Segment (items[0]) wurde verlaengert, NICHT die Insel
    assert items[0]["end"] == pytest.approx(12.0)
    assert items[0]["source_end"] == pytest.approx(12.0)
    assert items[1]["end"] == pytest.approx(4.0)  # Insel unangetastet
    assert items[2]["start"] == 12.0 and items[2]["end"] == 14.0  # locked
    # Luecke REAL zu: Validator besteht
    _validate_video_timeline_gaps(
        [{"start": i["start"], "end": i["end"]} for i in items]
    )


def test_b769_f1_open_gap_is_reported_unclosable_never_closed_but_open():
    """F-1 Kern (ehrliches Reporting): reicht das Restmaterial nicht, um das
    REALE prev_end an den Anker zu bringen, MUSS die Luecke als unclosable
    gemeldet werden — nie 'geschlossen aber offen'."""
    from services.export._common import heal_video_timeline_gaps

    items = [
        # Max-End-Segment OHNE Restmaterial (source_end == clip_duration)
        {"start": 0.0, "end": 10.0, "locked": False,
         "source_end": 10.0, "source_duration": 10.0, "clip_duration": 10.0},
        # Insel ebenfalls OHNE Restmaterial — nirgends Material, die Luecke
        # 10->12 ist real nicht schliessbar. Vertrag: EHRLICH melden.
        {"start": 2.0, "end": 4.0, "locked": False,
         "source_end": 2.0, "source_duration": 2.0, "clip_duration": 2.0},
        {"start": 12.0, "end": 14.0, "locked": True,
         "source_end": 2.0, "source_duration": 2.0, "clip_duration": 60.0},
    ]
    result = heal_video_timeline_gaps(items)

    # Kein Material nirgends -> Luecke 10->12 offen UND gemeldet
    assert result["unclosable"] == [(10.0, 12.0)]
    # Und NICHT zusaetzlich als geschlossen gezaehlt
    assert result["gaps_closed"] == 0
    with pytest.raises(ValueError, match="Timeline gap"):
        _validate_video_timeline_gaps(
            [{"start": i["start"], "end": i["end"]} for i in items]
        )


def test_b769_first_segment_locked_at_t_gt_0_is_unclosable():
    """Reviewer-Fall A (nachgebaut): erstes Segment locked bei t>0 — kein
    Vorgaenger vorhanden, Luecke ab 0.0 unschliessbar, locked unveraendert."""
    from services.export._common import heal_video_timeline_gaps

    items = [
        {"start": 3.0, "end": 8.0, "locked": True,
         "source_end": 5.0, "source_duration": 5.0, "clip_duration": 60.0},
        {"start": 8.0, "end": 12.0, "locked": False,
         "source_end": 4.0, "source_duration": 4.0, "clip_duration": 60.0},
    ]
    result = heal_video_timeline_gaps(items)

    assert result["unclosable"] == [(0.0, 3.0)]
    assert items[0]["start"] == 3.0 and items[0]["end"] == 8.0


def test_b769_video_end_before_audio_end_is_not_a_validator_error():
    """Pflichtvertrag Ende (dokumentiert): _validate_video_timeline_gaps
    prueft NUR Luecken ZWISCHEN Segmenten ab 0.0s — ein Video-Ende vor dem
    Audio-Ende (real: 5530.0s vs 5531.0s) ist KEIN Validator-Fehler und
    bricht den Export nicht. Keine in-memory-Behandlung noetig."""
    segs = [{"start": 0.0, "end": 5530.0}]
    _validate_video_timeline_gaps(segs)  # darf nicht werfen


def test_b769_repro_gap_before_locked_row_survives_repair(test_engine, monkeypatch):
    """Reale Konstellation aus new_test_august: 2.668s-Luecke vor locked Row.

    Vor Fix (RED): repair laesst die Luecke stehen, Validator wirft
    ``ValueError: Timeline gap vor Video-Segment 2: 3523.886s bis 3526.554s``.
    Nach Fix (GREEN): repair fuellt die Luecke aus ungenutztem Quellmaterial
    des Vorgaengers, Validator besteht, locked Row unveraendert.
    """
    import services.timeline_service as ts_mod
    monkeypatch.setattr(ts_mod, "engine", test_engine)

    with DBSession(test_engine) as s:
        p = Project(name="b769-repro", path="/tmp/b769-repro")
        s.add(p)
        s.flush()
        # Vorgaenger-Clip hat genug Restmaterial (3600s Clip, nur bis
        # 3523.886s genutzt -> 76s spare).
        clip_a = VideoClip(
            project_id=p.id, file_path="/tmp/b769-a.mp4", duration=3600.0,
        )
        clip_b = VideoClip(
            project_id=p.id, file_path="/tmp/b769-b.mp4", duration=10.0,
        )
        s.add_all([clip_a, clip_b])
        s.flush()
        s.add(TimelineEntry(
            project_id=p.id, track="video", media_id=clip_a.id,
            start_time=0.0, end_time=3523.886,
            source_start=0.0, source_end=3523.886,
            lane=0, locked=False,
        ))
        # Locked Anker exakt wie Entry 990: start 3526.554 -> Luecke 2.668s
        s.add(TimelineEntry(
            project_id=p.id, track="video", media_id=clip_b.id,
            start_time=3526.554, end_time=3533.554,
            source_start=0.1519, source_end=7.1519,
            lane=0, locked=True,
        ))
        s.commit()
        pid = p.id

    ts_mod.repair_timeline_integrity(pid)

    rows = _load_video_rows(test_engine, pid)
    # Locked-Vertrag: Anker unveraendert
    locked = [r for r in rows if r.locked]
    assert len(locked) == 1
    assert locked[0].start_time == pytest.approx(3526.554)
    assert locked[0].end_time == pytest.approx(3533.554)
    # Invariante: Export-Validator MUSS bestehen (wirft vor Fix ValueError)
    _validate_video_timeline_gaps(_rows_to_segments(rows))


def test_b769_repair_compaction_must_not_open_gap_before_locked(
    test_engine, monkeypatch,
):
    """Der 00:59-Lauf: Luecken ZWISCHEN unlocked Rows werden links-kompaktiert,
    dadurch ENTSTEHT die Luecke vor dem locked Anker erst. Auch die muss zu."""
    import services.timeline_service as ts_mod
    monkeypatch.setattr(ts_mod, "engine", test_engine)

    with DBSession(test_engine) as s:
        p = Project(name="b769-compact", path="/tmp/b769-compact")
        s.add(p)
        s.flush()
        clips = [
            VideoClip(project_id=p.id, file_path=f"/tmp/b769-c{i}.mp4",
                      duration=100.0)
            for i in range(3)
        ]
        s.add_all(clips)
        s.flush()
        # Unlocked: (0..5) und (10..15) — Luecke 5..10 wird kompaktiert,
        # danach endet unlocked Material bei 10.0.
        s.add(TimelineEntry(
            project_id=p.id, track="video", media_id=clips[0].id,
            start_time=0.0, end_time=5.0, source_start=0.0, source_end=5.0,
            lane=0, locked=False,
        ))
        s.add(TimelineEntry(
            project_id=p.id, track="video", media_id=clips[1].id,
            start_time=10.0, end_time=15.0, source_start=0.0, source_end=5.0,
            lane=0, locked=False,
        ))
        # Locked Anker bei 20..24 -> nach Kompaktierung Luecke 10..20 (10s)
        s.add(TimelineEntry(
            project_id=p.id, track="video", media_id=clips[2].id,
            start_time=20.0, end_time=24.0, source_start=0.0, source_end=4.0,
            lane=0, locked=True,
        ))
        s.commit()
        pid = p.id

    result = ts_mod.repair_timeline_integrity(pid)
    assert result["video_gaps_closed"] >= 1

    rows = _load_video_rows(test_engine, pid)
    locked = [r for r in rows if r.locked]
    assert len(locked) == 1
    assert locked[0].start_time == pytest.approx(20.0)
    assert locked[0].end_time == pytest.approx(24.0)
    _validate_video_timeline_gaps(_rows_to_segments(rows))


def test_b769_property_repaired_timeline_always_passes_validator(
    test_engine, monkeypatch,
):
    """50 seeded Zufalls-Timelines mit kuenstlichen Luecken/Overlaps + locked
    Ankern -> nach repair IMMER validator-gruen, locked nie verschoben.

    Dokumentierte Grenze (kein Generator-Fall): eine Luecke DIREKT ZWISCHEN
    zwei benachbarten locked Ankern ist ohne Lock-Bruch mathematisch nicht
    schliessbar (kein Material dazwischen, Anker unantastbar). Repair loggt
    dafuer eine B-769-Warnung; der Generator erzeugt deshalb keine zwei
    locked Rows ohne unlocked Row dazwischen.
    """
    import services.timeline_service as ts_mod
    monkeypatch.setattr(ts_mod, "engine", test_engine)

    rnd = random.Random(1337)  # fester Seed — deterministisch, kein time-based

    for case in range(50):
        with DBSession(test_engine) as s:
            p = Project(name=f"b769-prop-{case}", path=f"/tmp/b769-prop-{case}")
            s.add(p)
            s.flush()
            pid = p.id
            n = rnd.randint(3, 12)
            cursor = 0.0
            locked_expected = []
            prev_was_locked = False
            prev_row_was_anchor = False
            for i in range(n):
                dur = round(rnd.uniform(0.5, 5.0), 4)
                # Erste 2 Rows immer unlocked, damit vor einem locked Anker
                # Material zum Auffuellen existiert; nie 2 locked direkt
                # hintereinander (siehe dokumentierte Grenze im Docstring).
                is_locked = (
                    i >= 2 and not prev_was_locked and rnd.random() < 0.25
                )
                prev_was_locked = is_locked
                if is_locked:
                    # Locked Anker bewusst MIT Luecke hinter dem bisherigen Ende
                    start = round(cursor + rnd.uniform(0.1, 3.0), 4)
                elif prev_row_was_anchor:
                    # Row direkt nach einem Anker darf nicht VOR dessen Ende
                    # starten — sonst entstuenden in SORTIERTER Reihenfolge
                    # doch zwei benachbarte Anker (dokumentierte Grenze).
                    start = round(cursor + rnd.uniform(0.0, 3.0), 4)
                else:
                    # Zufaellige Luecke ODER Overlap
                    start = round(max(0.0, cursor + rnd.uniform(-2.0, 3.0)), 4)
                prev_row_was_anchor = is_locked
                end = round(start + dur, 4)
                clip = VideoClip(
                    project_id=pid,
                    file_path=f"/tmp/b769-prop-{case}-{i}.mp4",
                    # Genug Restmaterial, damit Backfill immer moeglich ist
                    duration=dur + 1000.0,
                )
                s.add(clip)
                s.flush()
                s.add(TimelineEntry(
                    project_id=pid, track="video", media_id=clip.id,
                    start_time=start, end_time=end,
                    source_start=0.0, source_end=dur,
                    lane=0, locked=is_locked,
                ))
                if is_locked:
                    locked_expected.append((start, end))
                cursor = max(cursor, end)
            s.commit()

        ts_mod.repair_timeline_integrity(pid)

        rows = _load_video_rows(test_engine, pid)
        locked_actual = sorted(
            (float(r.start_time), float(r.end_time))
            for r in rows if r.locked
        )
        assert locked_actual == sorted(locked_expected), (
            f"case {case}: locked Rows verschoben"
        )
        try:
            _validate_video_timeline_gaps(_rows_to_segments(rows))
        except ValueError as exc:  # pragma: no cover - Fehlerpfad
            pytest.fail(
                f"case {case}: Repair-Ergebnis besteht Validator nicht: {exc}"
            )
