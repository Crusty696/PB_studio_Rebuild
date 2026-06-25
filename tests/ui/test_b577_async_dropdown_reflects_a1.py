"""B-577 — Async-Combo-Refresh muss (wie B-569) den A1-Lane-Track zeigen.

Regression von B-569: ``_refresh_director_combos`` waehlt den A1-Audio-Track,
ABER der async-Pfad ``_apply_refreshed_data`` (laeuft beim Projekt-Open ueber
_on_project_changed -> _refresh_media_table -> _apply_refreshed_data) fuellt die
audio_combo NEU und waehlte nur preferred/first — OHNE A1-Logik. Nach
Projekt-Open zeigte das Dropdown wieder den falschen Track.

Behavioraler Test: Projekt mit zwei Audio-Tracks. Der NICHT-erste und NICHT-
analysierte Track liegt in der A1-Lane (timeline_entries track="audio"). Nach
``_apply_refreshed_data`` muss audio_combo.currentData() == A1-media_id sein.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QComboBox


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_b577_async_path_reflects_a1(
    qapp, test_engine, db_session, project, video_clip, monkeypatch
):
    from types import SimpleNamespace

    import database
    from ui.controllers.media_table import MediaTableController

    # Track 2: erster + analysiert (bekaeme ohne A1-Logik den Vorzug).
    analysed_first = database.AudioTrack(
        id=2,
        project_id=project.id,
        file_path="/tmp/normalize.wav",
        title="Normalize",
        bpm=128.0,
    )
    # Track 3: weder erster noch analysiert — aber LIEGT in der A1-Lane.
    a1_track = database.AudioTrack(
        id=3,
        project_id=project.id,
        file_path="/tmp/zyce.wav",
        title="Zyce",
    )
    db_session.add_all([analysed_first, a1_track])
    db_session.add(
        database.TimelineEntry(
            project_id=project.id,
            track="audio",
            media_id=a1_track.id,
            start_time=0.0,
        )
    )
    db_session.commit()

    # _apply_refreshed_data ermittelt das aktive Projekt ueber get_active_project_id.
    monkeypatch.setattr(database, "get_active_project_id", lambda: project.id)

    audio_combo = QComboBox()
    video_combo = QComboBox()
    refresh_audio_calls = []
    window = SimpleNamespace(
        logger=SimpleNamespace(debug=lambda *args, **kwargs: None),
        audio_combo=audio_combo,
        video_combo=video_combo,
        _schnitt_coordinator=SimpleNamespace(refresh_audio=refresh_audio_calls.append),
    )

    # Reihenfolge wie aus get_all_audio: analysierter/erster Track zuerst.
    audios = [
        {"id": 2, "title": "Normalize", "bpm": 128.0},
        {"id": 3, "title": "Zyce", "bpm": None},
    ]
    videos = [{"id": video_clip.id, "title": "Video"}]

    MediaTableController(window)._apply_refreshed_data(videos, audios, True)

    assert audio_combo.currentData() == 3, (
        "B-577-Regression: async _apply_refreshed_data ignoriert die A1-Lane "
        "und zeigt den falschen Audio-Track."
    )
    assert refresh_audio_calls == [3]
