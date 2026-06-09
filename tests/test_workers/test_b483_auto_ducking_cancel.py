from __future__ import annotations

import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from workers.audio import AutoDuckingWorker

def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

def test_auto_ducking_worker_user_cancel():
    _ensure_qapp()

    worker = AutoDuckingWorker(
        music_path="music.wav",
        voice_path="voice.wav",
        output_path="output.wav"
    )

    error_messages = []
    worker.error.connect(error_messages.append)

    # Mock create_ducked_audio to raise an exception
    # and call worker.cancel() during its execution to simulate user cancellation.
    def mock_create_ducked_audio(*args, **kwargs):
        worker.cancel()
        raise RuntimeError("Mock error during ducking process")

    with patch("services.ai_audio_service.AutoDucker.create_ducked_audio", side_effect=mock_create_ducked_audio):
        worker.run()

    assert len(error_messages) == 1
    assert "abgebrochen" in error_messages[0]
    assert "User-Cancel" in error_messages[0]
