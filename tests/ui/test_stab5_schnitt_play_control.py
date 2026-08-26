from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ui.workspaces.schnitt.tab_schnitt import SchnittTabSchnitt


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_schnitt_preview_transport_controls_real_preview_state(monkeypatch) -> None:
    _qapp()
    tab = SchnittTabSchnitt()
    preview = tab.video_preview
    started_at: list[float] = []
    teardown_calls: list[bool] = []

    preview._current_time = 12.0
    monkeypatch.setattr(preview, "play_from", started_at.append)
    tab.btn_play.click()
    assert started_at == [12.0]

    preview.position_changed.emit(12.0, 65.0)
    assert tab.time_label.text() == "00:12 / 01:05"

    preview.playback_state_changed.emit(True)
    assert tab.btn_play.text() == "⏸"

    preview._is_playing = True
    monkeypatch.setattr(preview, "_teardown_stream", lambda: teardown_calls.append(True))
    tab.btn_stop.click()
    assert teardown_calls == [True]
    assert preview._is_playing is False
    assert tab.btn_play.text() == "▶"
