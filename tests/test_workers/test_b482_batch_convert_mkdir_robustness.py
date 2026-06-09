from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from workers.import_export import BatchConvertWorker

def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

def test_batch_convert_mkdir_error_skips_file_and_continues(tmp_path):
    _ensure_qapp()

    # Create two input files
    file1 = tmp_path / "read_only_dir" / "video1.mp4"
    file2 = tmp_path / "normal_dir" / "video2.mp4"
    
    file1.parent.mkdir(parents=True, exist_ok=True)
    file2.parent.mkdir(parents=True, exist_ok=True)
    file1.touch()
    file2.touch()

    worker = BatchConvertWorker(
        [
            {"file_path": str(file1)},
            {"file_path": str(file2)},
        ],
        resolution="1920x1080",
        fps="30",
        vcodec="libx264",
        ext=".mp4"
    )

    progress_emitted = []
    worker.progress.connect(lambda p, msg: progress_emitted.append((p, msg)))

    original_mkdir = Path.mkdir
    
    def mock_mkdir(self, *args, **kwargs):
        # Raise OSError only for the first output directory
        if "read_only_dir" in str(self):
            raise OSError("Permission denied (Mock)")
        return original_mkdir(self, *args, **kwargs)

    # We mock Popen so that the second video doesn't actually call ffmpeg
    mock_popen = MagicMock()
    mock_process = MagicMock()
    mock_process.poll.return_value = 0  # Process finished instantly
    mock_process.stdout.readline.return_value = b""
    mock_process.stderr.readline.return_value = b""
    mock_popen.return_value = mock_process

    with patch.object(Path, "mkdir", autospec=True, side_effect=mock_mkdir), \
         patch("workers.import_export.subprocess.Popen", mock_popen):
        worker.run()

    # Check that we skipped the first video and processed the second
    # progress_emitted contains (progress_percent, message)
    skip_messages = [msg for _, msg in progress_emitted if "SKIP" in msg]
    convert_messages = [msg for _, msg in progress_emitted if "[Convert]" in msg]

    assert len(skip_messages) == 1
    assert "video1.mp4" in skip_messages[0]
    assert "Permission denied (Mock)" in skip_messages[0]

    assert len(convert_messages) == 1
    assert "video2.mp4" in convert_messages[0]
