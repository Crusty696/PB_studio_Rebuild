"""B-921: Der Auto-Edit legt die Tonspur mit auf die Timeline.

Vorher entstanden beim Auto-Edit ausschliesslich Video-Segmente. Die Musik kam
nur ueber den separaten Button "Zur Timeline hinzufuegen" dorthin — wer dem
gefuehrten Ablauf folgte, exportierte ein stummes Video.

Geprueft wird der Vertrag von ``apply_auto_edit_segments``:
- mit ``audio_id`` entsteht genau eine Tonspur ueber die volle Trackdauer
- eine bereits vorhandene Tonspur bleibt unangetastet (auch eine andere)
- ohne ``audio_id`` bleibt das alte Verhalten erhalten
- ein unbekannter Track fuehrt nicht zum Absturz
"""
from __future__ import annotations

import pytest

from database import AudioTrack, Project, TimelineEntry, VideoClip
from services.timeline_service import apply_auto_edit_segments


@pytest.fixture
def project_with_media(test_engine):
    """Projekt mit einem analysierten Audio-Track und zwei Videoclips."""
    from sqlalchemy.orm import Session

    with Session(test_engine) as s:
        project = Project(name="B-921", path=r"C:\tmp\b921")
        s.add(project)
        s.flush()

        audio = AudioTrack(
            project_id=project.id,
            file_path=r"C:\tmp\b921\track.mp3",
            title="B-921 Track",
            duration=337.1,
        )
        s.add(audio)

        clips = [
            VideoClip(
                project_id=project.id,
                file_path=rf"C:\tmp\b921\clip{i}.mp4",
                duration=30.0,
            )
            for i in (1, 2)
        ]
        s.add_all(clips)
        s.commit()

        return {
            "project_id": project.id,
            "audio_id": audio.id,
            "video_ids": [c.id for c in clips],
        }


def _segments(video_ids: list[int]) -> list[dict]:
    return [
        {"media_id": video_ids[0], "start": 0.0, "end": 5.0,
         "source_start": 0.0, "source_end": 5.0},
        {"media_id": video_ids[1], "start": 5.0, "end": 12.0,
         "source_start": 0.0, "source_end": 7.0},
    ]


def _entries(engine, project_id: int, track: str) -> list[TimelineEntry]:
    from sqlalchemy.orm import Session

    with Session(engine) as s:
        return (
            s.query(TimelineEntry)
            .filter_by(project_id=project_id, track=track)
            .order_by(TimelineEntry.start_time)
            .all()
        )


def test_auto_edit_legt_tonspur_mit_an(test_engine, project_with_media):
    """Kern von B-921: mit audio_id entsteht eine Tonspur ueber die Trackdauer."""
    ctx = project_with_media

    inserted = apply_auto_edit_segments(
        _segments(ctx["video_ids"]),
        project_id=ctx["project_id"],
        audio_id=ctx["audio_id"],
    )

    audio_rows = _entries(test_engine, ctx["project_id"], "audio")
    assert len(audio_rows) == 1, "genau eine Tonspur erwartet"

    row = audio_rows[0]
    assert row.media_id == ctx["audio_id"]
    assert row.start_time == pytest.approx(0.0)
    assert row.end_time == pytest.approx(337.1, abs=1e-3), (
        "Tonspur muss die volle Trackdauer abdecken"
    )

    video_rows = _entries(test_engine, ctx["project_id"], "video")
    assert len(video_rows) == 2, "Video-Segmente bleiben unveraendert"
    assert inserted == 3, "Rueckgabewert zaehlt Video-Segmente plus Tonspur"


def test_vorhandene_tonspur_bleibt_unangetastet(test_engine, project_with_media):
    """Liegt bereits eine andere Spur, ersetzt der Auto-Edit sie nicht.

    Der schuetzenswerte Fall: Der Nutzer hat Track B auf die Timeline gelegt,
    der Auto-Edit laeuft mit Track A. Dann darf weder Track B verschwinden noch
    eine zweite Spur danebenliegen.
    """
    from sqlalchemy.orm import Session

    ctx = project_with_media
    with Session(test_engine) as s:
        other = AudioTrack(
            project_id=ctx["project_id"],
            file_path=r"C:\tmp\b921\other.mp3",
            title="andere Musik",
            duration=120.0,
        )
        s.add(other)
        s.flush()
        other_id = other.id
        s.add(TimelineEntry(
            project_id=ctx["project_id"], track="audio",
            media_id=other_id, start_time=0.0, end_time=120.0, lane=0,
        ))
        s.commit()

    apply_auto_edit_segments(
        _segments(ctx["video_ids"]),
        project_id=ctx["project_id"],
        audio_id=ctx["audio_id"],
    )

    audio_rows = _entries(test_engine, ctx["project_id"], "audio")
    assert len(audio_rows) == 1, "keine zweite Tonspur anlegen"
    assert audio_rows[0].media_id == other_id, (
        "die bereits gesetzte Spur darf nicht ersetzt werden"
    )


def test_ohne_audio_id_bleibt_es_beim_alten_verhalten(test_engine, project_with_media):
    """Ohne audio_id entstehen weiterhin ausschliesslich Video-Segmente."""
    ctx = project_with_media

    inserted = apply_auto_edit_segments(
        _segments(ctx["video_ids"]),
        project_id=ctx["project_id"],
    )

    assert _entries(test_engine, ctx["project_id"], "audio") == []
    assert len(_entries(test_engine, ctx["project_id"], "video")) == 2
    assert inserted == 2


def test_unbekannter_audio_track_bricht_den_apply_nicht(test_engine, project_with_media):
    """Ein ungueltiger Verweis darf den Auto-Edit nicht scheitern lassen."""
    ctx = project_with_media

    inserted = apply_auto_edit_segments(
        _segments(ctx["video_ids"]),
        project_id=ctx["project_id"],
        audio_id=999999,
    )

    assert _entries(test_engine, ctx["project_id"], "audio") == []
    assert len(_entries(test_engine, ctx["project_id"], "video")) == 2
    assert inserted == 2
