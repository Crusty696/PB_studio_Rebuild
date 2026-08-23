"""B-873: blockierter Combo-Refresh muss sichtbare Videoauswahl synchronisieren."""
from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QComboBox


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _window_with_preview_probe():
    audio_combo = QComboBox()
    video_combo = QComboBox()
    preview_calls: list[tuple[int, int | None]] = []
    video_signals: list[int] = []
    video_combo.currentIndexChanged.connect(video_signals.append)

    edit_workspace = SimpleNamespace(
        _on_video_combo_changed=lambda index: preview_calls.append(
            (int(index), video_combo.currentData())
        )
    )
    window = SimpleNamespace(
        logger=SimpleNamespace(debug=lambda *args, **kwargs: None),
        audio_combo=audio_combo,
        video_combo=video_combo,
        edit_workspace=edit_workspace,
    )
    return window, preview_calls, video_signals


def test_b873_sync_refresh_initializes_visible_video_preview(
    qapp, test_engine, db_session, project, video_clip
):
    from ui.controllers.media_table import MediaTableController

    window, preview_calls, video_signals = _window_with_preview_probe()

    MediaTableController(window)._refresh_director_combos(project.id)

    assert window.video_combo.currentData() == video_clip.id
    assert video_signals == [], "B-315: blockierter Refresh darf keine Signalkaskade feuern"
    assert preview_calls == [(window.video_combo.currentIndex(), video_clip.id)]


def test_b873_async_refresh_initializes_visible_video_preview(qapp, monkeypatch):
    import database
    from ui.controllers.media_table import MediaTableController

    monkeypatch.setattr(database, "get_active_project_id", lambda: None)
    window, preview_calls, video_signals = _window_with_preview_probe()

    MediaTableController(window)._apply_refreshed_data(
        videos=[{"id": 42, "title": "Neon Video"}],
        audios=[],
        also_combos=True,
    )

    assert window.video_combo.currentData() == 42
    assert video_signals == [], "B-315: blockierter Refresh darf keine Signalkaskade feuern"
    assert preview_calls == [(window.video_combo.currentIndex(), 42)]
