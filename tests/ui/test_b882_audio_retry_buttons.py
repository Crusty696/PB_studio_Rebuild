"""B-882: Aktiver Audio-Combo-Track ist gueltige Einzeltrack-Auswahl."""

from unittest.mock import MagicMock


def test_b882_single_track_falls_back_to_active_audio_combo(qapp, monkeypatch):
    from ui.controllers.audio_analysis import AudioAnalysisController

    ctrl = AudioAnalysisController.__new__(AudioAnalysisController)
    ctrl.window = MagicMock()

    model = MagicMock()
    model.get_checked_ids.return_value = []
    view = MagicMock()
    view.model.return_value = model
    view.selectionModel.return_value.selectedRows.return_value = []
    ctrl.window.audio_pool_table = view
    ctrl.window.audio_combo.currentData.return_value = 42

    fake_track = MagicMock()
    fake_track.id = 42
    fake_track.file_path = "/x.mp3"
    fake_track.title = "Aktiver Track"
    fake_track.bpm = 120.0

    fake_session = MagicMock()
    fake_session.execute.return_value.first.return_value = fake_track
    fake_ctx = MagicMock()
    fake_ctx.__enter__.return_value = fake_session
    fake_ctx.__exit__.return_value = False

    import sqlalchemy.orm as orm

    monkeypatch.setattr(orm, "Session", lambda engine: fake_ctx)

    result = ctrl._get_selected_audio_track()

    assert result == (42, "/x.mp3", "Aktiver Track", 120.0)
