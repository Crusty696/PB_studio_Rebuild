"""Task E1: get_all_audio / get_all_video ohne Eager-Load-Lawine.

database/models.py definiert mapper-weite Eager-Loads (AudioTrack:
waveform_data/beatgrid lazy='joined', structure_segments/hotcues/
audio_video_anchors lazy='selectin'; VideoClip: scenes/audio_video_anchors
lazy='selectin'). get_all_audio/get_all_video brauchen aber NUR
Skalar-Spalten — die Eager-Loads luden pro Track MB-grosse
Waveform-/Beatgrid-JSONs und feuerten zusaetzliche selectin-Queries.

Baseline (gemessen VOR dem lazyload-Fix, synthetische DB: 5 Tracks mit
Waveform/Beatgrid/Segments + 5 Clips mit Scenes, Status-Refresh gestubbt):
    get_all_audio: 6 Queries (1 Haupt-SELECT mit joined waveform/beatgrid/
                   project + selectin segments/hotcues/anchors)
    get_all_video: 4 Queries (1 Haupt-SELECT mit joined project +
                   selectin scenes/anchors)
Nach Fix (.options(lazyload("*"))): je exakt 1 Query, identische
Ergebnis-Dicts (alle Werte hart gepinnt).
"""
from __future__ import annotations

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from database import (
    AudioTrack,
    Beatgrid,
    Project,
    Scene,
    StructureSegment,
    VideoClip,
    WaveformData,
)

BASELINE_AUDIO_QUERIES = 6  # gemessen 2026-07-13 vor dem Fix
BASELINE_VIDEO_QUERIES = 4  # gemessen 2026-07-13 vor dem Fix


@pytest.fixture
def seeded_db(test_engine):
    """5 AudioTracks (mit Waveform/Beatgrid/Segments) + 5 VideoClips (mit Scenes)."""
    with Session(test_engine) as s:
        s.add(Project(id=1, name="P", path="."))
        s.flush()
        for i in range(1, 6):
            s.add(AudioTrack(
                id=i, project_id=1, file_path=f"/a/{i}.mp3", title=f"A{i}",
                duration=100.0 + i, bpm=120.0 + i,
                key="8A" if i % 2 else None,
                mood="dark" if i == 1 else None,
                genre="psy" if i == 1 else None,
                energy_curve=[0.5] * 4,
                stem_vocals_path="v.wav" if i == 1 else None,
                stem_drums_path="d.wav" if i == 1 else None,
            ))
            s.add(WaveformData(
                audio_track_id=i, num_samples=1000 * i, duration=100.0 + i,
                band_low=[0.1] * 50, band_mid=[0.2] * 50, band_high=[0.3] * 50,
            ))
            s.add(Beatgrid(
                audio_track_id=i, bpm=120.0 + i, offset=0.0,
                beat_positions=[float(b) for b in range(20)],
            ))
            for k in range(3):
                s.add(StructureSegment(
                    audio_track_id=i, start_time=k * 10.0,
                    end_time=k * 10.0 + 10.0, label="DROP", energy=0.8,
                ))
        for i in range(1, 6):
            s.add(VideoClip(
                id=i, project_id=1, file_path=f"/v/{i}.mp4",
                duration=30.0 + i, width=1920, height=1080, fps=30.0,
                codec="h264",
            ))
            for k in range(4):
                s.add(Scene(
                    video_clip_id=i, start_time=k * 5.0, end_time=k * 5.0 + 5.0,
                ))
        s.commit()
    return test_engine


@pytest.fixture
def query_counter(seeded_db):
    statements: list[str] = []

    def _on(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(seeded_db, "before_cursor_execute", _on)
    yield statements
    event.remove(seeded_db, "before_cursor_execute", _on)


@pytest.fixture
def stubbed_status(monkeypatch):
    """Status-Refresh stubben — dessen Query-Count ist Task E2, nicht E1."""
    from services import analysis_status_service as ass
    monkeypatch.setattr(ass, "infer_many_from_db", lambda *a, **k: None)
    monkeypatch.setattr(ass, "get_completion_percent_map", lambda *a, **k: {})


def test_e1_get_all_audio_single_query_and_identical_dicts(
    query_counter, stubbed_status
):
    import services.ingest_service as svc

    result = svc.get_all_audio(project_id=1)

    n = len(query_counter)
    assert n < BASELINE_AUDIO_QUERIES, (
        f"E1: get_all_audio feuert {n} Queries — keine Verbesserung gegenueber "
        f"Baseline {BASELINE_AUDIO_QUERIES} (Eager-Load-Lawine zurueck?)"
    )
    assert n == 1, (
        f"E1: get_all_audio muss mit lazyload('*') exakt 1 Query feuern, war {n}:\n"
        + "\n".join(st.split(chr(10))[0][:120] for st in query_counter)
    )
    # Waveform-/Beatgrid-Blobs duerfen nicht mitgeladen werden
    joined = query_counter[0].lower()
    assert "waveform_data" not in joined and "beatgrids" not in joined, (
        "E1: Haupt-SELECT joint weiterhin waveform_data/beatgrids"
    )

    # Ergebnis-Dicts identisch zur Baseline (vor dem Fix gemessen, hart gepinnt)
    assert result[0] == {
        "id": 1, "title": "A1", "file_path": "/a/1.mp3", "type": "Audio",
        "bpm": 121.0, "stems": "2/4", "key": "8A", "mood": "dark",
        "genre": "psy", "duration": 101.0, "energy_curve": [0.5] * 4,
        "analysis_percent": 0.0,
    }
    assert result[1] == {
        "id": 2, "title": "A2", "file_path": "/a/2.mp3", "type": "Audio",
        "bpm": 122.0, "stems": "-", "key": None, "mood": None,
        "genre": None, "duration": 102.0, "energy_curve": [0.5] * 4,
        "analysis_percent": 0.0,
    }
    assert [r["id"] for r in result] == [1, 2, 3, 4, 5]


def test_e1_get_all_video_single_query_and_identical_dicts(
    query_counter, stubbed_status
):
    import services.ingest_service as svc

    result = svc.get_all_video(project_id=1)

    n = len(query_counter)
    assert n < BASELINE_VIDEO_QUERIES, (
        f"E1: get_all_video feuert {n} Queries — keine Verbesserung gegenueber "
        f"Baseline {BASELINE_VIDEO_QUERIES} (Eager-Load-Lawine zurueck?)"
    )
    assert n == 1, (
        f"E1: get_all_video muss mit lazyload('*') exakt 1 Query feuern, war {n}:\n"
        + "\n".join(st.split(chr(10))[0][:120] for st in query_counter)
    )
    assert "scenes" not in query_counter[0].lower(), (
        "E1: get_all_video laedt weiterhin Scenes (selectin)"
    )

    assert result[0] == {
        "id": 1, "title": "1", "file_path": "/v/1.mp4", "type": "Video",
        "resolution": "1920x1080", "fps": 30.0, "codec": "h264",
        "stems": "-", "analysis_percent": 0.0,
    }
    assert [r["id"] for r in result] == [1, 2, 3, 4, 5]
