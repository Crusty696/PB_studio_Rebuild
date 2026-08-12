"""B-569 — SCHNITT-Audio-Dropdown muss den A1-Lane-Track zeigen.

Originalbefund: Audio-ID (Zyce) lag in der A1-Lane (timeline_entries track="audio"),
das Dropdown zeigte aber einen anderen Track (ersten/analysierten). ``
_refresh_director_combos`` waehlte den Default unabhaengig vom A1-Inhalt.

Wiring-Guard im Stil von ``test_b321`` / ``test_b562``. Der behaviorale
Live-Beweis kommt aus dem pb-gui-tester (Zyce in A1 -> Dropdown == Zyce).
"""
from __future__ import annotations

import inspect
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


def test_refresh_director_combos_prefers_a1_audio_track() -> None:
    from ui.controllers.media_table import MediaTableController

    # B-577: Die A1-Lookup-Logik wurde in den gemeinsamen Helper
    # ``_a1_audio_combo_index`` extrahiert (von sync- UND async-Pfad genutzt).
    # _refresh_director_combos muss diesen Helper fuer die Auswahl heranziehen.
    combos_source = inspect.getsource(
        MediaTableController._refresh_director_combos
    )
    helper_source = inspect.getsource(
        MediaTableController._a1_audio_combo_index
    )

    # Auswahl muss den tatsaechlichen A1-Audio-Entry beruecksichtigen.
    assert 'track="audio"' in helper_source or "track='audio'" in helper_source, (
        "B-569-Regression: _a1_audio_combo_index muss den A1-Audio-Entry "
        "(timeline_entries track=audio) fuer die Dropdown-Auswahl heranziehen."
    )
    assert "a1_audio_index" in combos_source
    assert "_a1_audio_combo_index" in combos_source
    assert "findData" in helper_source


def test_b569_sync_path_reflects_a1_behavioral(
    qapp, test_engine, db_session, project, video_clip, monkeypatch
):
    """Behavioraler Gegenbeweis fuer den SYNC-Pfad (`_refresh_director_combos`).

    Der Live-Verify vom 2026-08-09 war nicht diskriminierend: das Testprojekt
    hatte nur EINEN Audio-Track, damit ist "A1-Auswahl" nicht von "nimm den
    einzigen/ersten Track" unterscheidbar. Dieser Test erzwingt die
    Unterscheidung: ZWEI Tracks, und der A1-Lane-Track ist weder der erste
    noch der analysierte. Ohne A1-Logik faellt die Auswahl auf den
    analysierten Track 2 -> Test rot.
    """
    from types import SimpleNamespace

    import database
    from ui.controllers.media_table import MediaTableController

    # Track 2: erster + analysiert (bpm gesetzt) -> Default ohne A1-Logik.
    analysed_first = database.AudioTrack(
        id=2,
        project_id=project.id,
        file_path="/tmp/normalize.wav",
        title="Normalize",
        bpm=128.0,
    )
    # Track 3: weder erster noch analysiert — liegt aber in der A1-Lane.
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

    audio_combo = QComboBox()
    video_combo = QComboBox()
    refresh_audio_calls = []
    window = SimpleNamespace(
        logger=SimpleNamespace(debug=lambda *args, **kwargs: None),
        audio_combo=audio_combo,
        video_combo=video_combo,
        _schnitt_coordinator=SimpleNamespace(refresh_audio=refresh_audio_calls.append),
    )

    MediaTableController(window)._refresh_director_combos(project_id=project.id)

    # Gegenprobe im Test selbst: beide Tracks MUESSEN im Combo stehen, sonst
    # wuerde die Assertion unten trivial durch einen Fallback erfuellt.
    assert audio_combo.count() == 3, "Erwartet: Platzhalter + 2 Audio-Tracks"
    assert audio_combo.findData(2) >= 0 and audio_combo.findData(3) >= 0

    assert audio_combo.currentData() == 3, (
        "B-569-Regression: _refresh_director_combos ignoriert die A1-Lane und "
        "waehlt den analysierten/ersten Track."
    )
    assert refresh_audio_calls == [3]
