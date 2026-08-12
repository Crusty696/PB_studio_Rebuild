"""B-811: ``infer_many_from_db`` fragte pro Medium statt einmal fuer alle.

Befund (2026-08-12, Klassensuche nach stummen Langlaeufern nach B-810):
``infer_many_from_db`` buendelte nur die AnalysisStatus-Abfrage. Die Fakten
holte es weiter PRO Medium — Video 2 Abfragen je Clip, Audio 4 je Track.
Gegen die reale Projekt-DB ``outputs/test-tabelle`` gemessen: 733
SQL-Statements fuer 366 Clips (2*N+1), 545 fuer 136 Audiotracks (4*N+1).

Der Aufruf haengt an ``get_all_video`` / ``get_all_audio``, also an JEDEM
Medien-Tabellen-Refresh (Projekt-Open, nach jedem Import) — und meldet
dabei nichts. Auf belegter DB kostet jede Rundreise zusaetzlich Wartezeit.

Beweis ist der Zaehltest, nicht die Stoppuhr: die Statement-Zahl darf nicht
mehr mit der Zahl der Medien wachsen.
"""

from __future__ import annotations

import pytest
from sqlalchemy import event

import database


def _count_statements(engine):
    """Zaehlt ausgefuehrte SQL-Statements auf *engine*."""
    box = {"n": 0}

    def _on_exec(conn, cursor, statement, parameters, context, executemany):
        box["n"] += 1

    event.listen(engine, "before_cursor_execute", _on_exec)
    box["stop"] = lambda: event.remove(engine, "before_cursor_execute", _on_exec)
    return box


def _make_clips(engine, count: int, tag: str = "a") -> list[int]:
    from database import Project, Scene, VideoClip
    from sqlalchemy.orm import Session

    ids: list[int] = []
    with Session(engine) as session:
        if session.get(Project, 1) is None:
            session.add(Project(id=1, name="P", path="p"))
            session.flush()
        for i in range(count):
            clip = VideoClip(
                project_id=1,
                file_path=f"c{tag}{i}.mp4",
                duration=10.0,
                width=1920,
                height=1080,
                fps=30.0,
                codec="h264",
            )
            session.add(clip)
            session.flush()
            ids.append(clip.id)
            session.add(
                Scene(
                    video_clip_id=clip.id,
                    start_time=0.0,
                    end_time=5.0,
                    ai_caption=f"caption {i}",
                )
            )
        session.commit()
    return ids


def _make_tracks(engine, count: int, tag: str = "a") -> list[int]:
    from database import AudioTrack, Beatgrid, Project, WaveformData
    from sqlalchemy.orm import Session

    ids: list[int] = []
    with Session(engine) as session:
        if session.get(Project, 1) is None:
            session.add(Project(id=1, name="P", path="p"))
            session.flush()
        for i in range(count):
            track = AudioTrack(
                project_id=1,
                file_path=f"t{tag}{i}.wav",
                key="Am",
                key_confidence=0.9,
                lufs=-14.0,
                mood="calm",
                genre="psy",
                stem_vocals_path=f"v{i}.wav",
            )
            session.add(track)
            session.flush()
            ids.append(track.id)
            session.add(
                Beatgrid(audio_track_id=track.id, bpm=140.0, beat_positions=[1.0, 2.0])
            )
            session.add(
                WaveformData(
                    audio_track_id=track.id,
                    num_samples=100,
                    duration=1.0,
                    band_low=[0.1],
                    band_mid=[0.2],
                    band_high=[0.3],
                )
            )
        session.commit()
    return ids


def _statuses(engine, media_type: str, ids: list[int]) -> dict:
    from database import AnalysisStatus
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        rows = (
            session.query(AnalysisStatus)
            .filter(
                AnalysisStatus.media_type == media_type,
                AnalysisStatus.media_id.in_(ids),
            )
            .all()
        )
        return {
            (r.media_id, r.step_key): (r.status, r.value_summary) for r in rows
        }


@pytest.mark.parametrize("media_type", ["video", "audio"])
def test_statement_count_does_not_grow_with_media_count(
    test_engine, monkeypatch, media_type
):
    """Kernbeweis: 10x so viele Medien duerfen NICHT 10x so viele Queries kosten.

    Gemessen wird der EINGESCHWUNGENE Lauf (zweiter Aufruf). Beim ersten Lauf
    schreibt ``_ensure_status_done`` je Medium und Schritt eine Zeile — dieses
    Wachstum ist gewollt und einmalig. Danach steht alles auf ``done`` und der
    Aufruf ist reines Lesen. Genau dieser Lesepfad lief bei JEDEM
    Medien-Tabellen-Refresh und war der N+1.
    """
    from services import analysis_status_service as svc

    monkeypatch.setattr(svc, "nullpool_session", database.nullpool_session)

    maker = _make_clips if media_type == "video" else _make_tracks

    few = maker(test_engine, 2, tag="few")
    svc.infer_many_from_db(media_type, few)  # warmlaufen
    counter = _count_statements(test_engine)
    svc.infer_many_from_db(media_type, few)
    n_few = counter["n"]
    counter["stop"]()

    many = maker(test_engine, 20, tag="many")
    svc.infer_many_from_db(media_type, many)  # warmlaufen
    counter = _count_statements(test_engine)
    svc.infer_many_from_db(media_type, many)
    n_many = counter["n"]
    counter["stop"]()

    assert n_many <= n_few, (
        f"{media_type}: 2 Medien kosteten {n_few} Statements, 20 Medien "
        f"{n_many}. Der Aufwand waechst weiter mit der Zahl der Medien — "
        "die Sammelabfragen greifen nicht (N+1)."
    )


@pytest.mark.parametrize("media_type", ["video", "audio"])
def test_bulk_path_yields_same_status_rows_as_single_path(
    test_engine, monkeypatch, media_type
):
    """Gleichheitsprobe: der Bulk-Pfad darf nichts anderes schreiben als der
    Einzelpfad ``infer_from_db``."""
    from services import analysis_status_service as svc

    monkeypatch.setattr(svc, "nullpool_session", database.nullpool_session)

    maker = _make_clips if media_type == "video" else _make_tracks
    ids = maker(test_engine, 5)

    svc.infer_many_from_db(media_type, ids)
    bulk = _statuses(test_engine, media_type, ids)

    from database import AnalysisStatus
    from sqlalchemy.orm import Session

    with Session(test_engine) as session:
        session.query(AnalysisStatus).delete()
        session.commit()

    for media_id in ids:
        svc.infer_from_db(media_type, media_id)
    single = _statuses(test_engine, media_type, ids)

    assert bulk, "Bulk-Pfad hat gar keine Status-Zeilen geschrieben."
    assert bulk == single, (
        "Bulk-Pfad und Einzelpfad liefern unterschiedliche Status-Zeilen — "
        "die Vorabladung aendert die Semantik."
    )


def test_video_without_scenes_gets_no_scene_status(test_engine, monkeypatch):
    """Abgrenzung: fehlende Szenen duerfen im Bulk-Pfad nicht zu einem
    faelschlich gesetzten scene_detection fuehren (leeres Prefetch-Fach)."""
    from database import Project, VideoClip
    from sqlalchemy.orm import Session
    from services import analysis_status_service as svc

    monkeypatch.setattr(svc, "nullpool_session", database.nullpool_session)

    with Session(test_engine) as session:
        session.add(Project(id=1, name="P", path="p"))
        session.flush()
        clip = VideoClip(
            project_id=1, file_path="x.mp4", duration=10.0,
            width=1920, height=1080, fps=30.0, codec="h264",
        )
        session.add(clip)
        session.commit()
        clip_id = clip.id

    svc.infer_many_from_db("video", [clip_id])
    steps = {k[1] for k in _statuses(test_engine, "video", [clip_id])}

    assert "metadata_extract" in steps
    assert "scene_detection" not in steps, (
        "Clip ohne Szenen bekam scene_detection=done — die Prefetch-Zuordnung "
        "vermischt Clips."
    )
