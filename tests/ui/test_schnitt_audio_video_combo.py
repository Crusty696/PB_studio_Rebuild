"""Tier-3-Sunset T3.2/T3.3: audio_combo + video_combo + btn_generate + btn_auto_edit
liegen auf dem SchnittEditorView (Header), nicht mehr auf der hidden EditWorkspace.
"""
from __future__ import annotations
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QComboBox, QPushButton


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_schnitt_editor_view_exposes_audio_video_combo(qapp):
    from ui.workspaces.schnitt.editor_view import SchnittEditorView

    view = SchnittEditorView()
    try:
        assert hasattr(view, "audio_combo"), "SchnittEditorView.audio_combo fehlt"
        assert hasattr(view, "video_combo"), "SchnittEditorView.video_combo fehlt"
        assert isinstance(view.audio_combo, QComboBox)
        assert isinstance(view.video_combo, QComboBox)
    finally:
        view.deleteLater()


def test_schnitt_editor_view_exposes_generate_and_auto_edit(qapp):
    from ui.workspaces.schnitt.editor_view import SchnittEditorView

    view = SchnittEditorView()
    try:
        assert hasattr(view, "btn_generate"), "SchnittEditorView.btn_generate fehlt"
        assert hasattr(view, "btn_auto_edit"), "SchnittEditorView.btn_auto_edit fehlt"
        assert isinstance(view.btn_generate, QPushButton)
        assert isinstance(view.btn_auto_edit, QPushButton)
        assert view.btn_generate.text() == "Timeline generieren"
        assert view.btn_auto_edit.text() == "Auto-Edit"
    finally:
        view.deleteLater()


def test_b314_director_combos_select_first_real_project_media(
    qapp, test_engine, db_session, project, audio_track, video_clip
):
    from types import SimpleNamespace

    import database
    from ui.controllers.media_table import MediaTableController

    db_session.add(
        database.AudioTrack(
            project_id=project.id,
            file_path="/tmp/second_audio.wav",
            title="Second Audio",
            bpm=126.0,
        )
    )
    db_session.add(
        database.VideoClip(
            project_id=project.id,
            file_path="/tmp/second_video.mp4",
            duration=8.0,
            width=1920,
            height=1080,
            fps=30.0,
        )
    )
    db_session.commit()

    audio_combo = QComboBox()
    video_combo = QComboBox()
    window = SimpleNamespace(
        logger=SimpleNamespace(debug=lambda *args, **kwargs: None),
        audio_combo=audio_combo,
        video_combo=video_combo,
    )

    MediaTableController(window)._refresh_director_combos(audio_track.project_id)

    assert audio_combo.currentData() == audio_track.id
    assert video_combo.currentData() == video_clip.id


def test_b315_director_combo_refresh_does_not_emit_selection_signals(
    qapp, test_engine, db_session, project, audio_track, video_clip
):
    from types import SimpleNamespace

    from ui.controllers.media_table import MediaTableController

    audio_combo = QComboBox()
    video_combo = QComboBox()
    audio_changes = []
    video_changes = []
    audio_combo.currentIndexChanged.connect(audio_changes.append)
    video_combo.currentIndexChanged.connect(video_changes.append)
    window = SimpleNamespace(
        logger=SimpleNamespace(debug=lambda *args, **kwargs: None),
        audio_combo=audio_combo,
        video_combo=video_combo,
    )

    MediaTableController(window)._refresh_director_combos(audio_track.project_id)

    assert audio_combo.currentData() == audio_track.id
    assert video_combo.currentData() == video_clip.id
    assert audio_changes == []
    assert video_changes == []


def test_b316_director_combo_refresh_syncs_schnitt_audio_without_signals(
    qapp, test_engine, db_session, project, audio_track, video_clip
):
    from types import SimpleNamespace

    from ui.controllers.media_table import MediaTableController

    audio_combo = QComboBox()
    video_combo = QComboBox()
    audio_changes = []
    video_changes = []
    refresh_audio_calls = []
    stem_calls = []
    audio_combo.currentIndexChanged.connect(audio_changes.append)
    video_combo.currentIndexChanged.connect(video_changes.append)
    window = SimpleNamespace(
        logger=SimpleNamespace(debug=lambda *args, **kwargs: None),
        audio_combo=audio_combo,
        video_combo=video_combo,
        _schnitt_coordinator=SimpleNamespace(refresh_audio=refresh_audio_calls.append),
        stems=SimpleNamespace(_update_stem_workspace=stem_calls.append),
    )

    MediaTableController(window)._refresh_director_combos(audio_track.project_id)

    assert audio_combo.currentData() == audio_track.id
    assert video_combo.currentData() == video_clip.id
    assert audio_changes == []
    assert video_changes == []
    assert refresh_audio_calls == [audio_track.id]
    assert stem_calls == [audio_track.id]


def test_b316_async_combo_refresh_syncs_schnitt_audio_without_signals(qapp):
    from types import SimpleNamespace

    from ui.controllers.media_table import MediaTableController

    audio_combo = QComboBox()
    video_combo = QComboBox()
    audio_changes = []
    video_changes = []
    refresh_audio_calls = []
    stem_calls = []
    audio_combo.currentIndexChanged.connect(audio_changes.append)
    video_combo.currentIndexChanged.connect(video_changes.append)
    window = SimpleNamespace(
        logger=SimpleNamespace(debug=lambda *args, **kwargs: None),
        audio_combo=audio_combo,
        video_combo=video_combo,
        _schnitt_coordinator=SimpleNamespace(refresh_audio=refresh_audio_calls.append),
        stems=SimpleNamespace(_update_stem_workspace=stem_calls.append),
    )
    audios = [{"id": 23, "title": "Podcast", "bpm": 136.4}]
    videos = [{"id": 42, "title": "Neon Video"}]

    MediaTableController(window)._apply_refreshed_data(videos, audios, True)

    assert audio_combo.currentData() == 23
    assert video_combo.currentData() == 42
    assert audio_changes == []
    assert video_changes == []
    assert refresh_audio_calls == [23]
    assert stem_calls == [23]


def test_b317_async_combo_refresh_prefers_analyzed_audio(qapp):
    from types import SimpleNamespace

    from ui.controllers.media_table import MediaTableController

    audio_combo = QComboBox()
    video_combo = QComboBox()
    refresh_audio_calls = []
    window = SimpleNamespace(
        logger=SimpleNamespace(debug=lambda *args, **kwargs: None),
        audio_combo=audio_combo,
        video_combo=video_combo,
        _schnitt_coordinator=SimpleNamespace(refresh_audio=refresh_audio_calls.append),
    )
    audios = [
        {"id": 3, "title": "tmpwn3ztkf7", "bpm": None, "duration": None},
        {"id": 2, "title": "02 Mai Podcast 19 - Kopie", "bpm": 136.4, "duration": 5531.005},
    ]
    videos = [{"id": 42, "title": "Neon Video"}]

    MediaTableController(window)._apply_refreshed_data(videos, audios, True)

    assert audio_combo.currentData() == 2
    assert refresh_audio_calls == [2]
