import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from unittest.mock import MagicMock, patch
import subprocess
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication
from workers.import_export import BatchConvertWorker


def test_b525_standardize_dialog_exposes_format_options_incl_copy():
    """B-525: der modale Ziel-Format-Dialog bietet Aufloesung/FPS/Container inkl.
    Copy und liefert die Auswahl-Strings, die _run_standardize erwartet."""
    QApplication.instance() or QApplication([])
    from ui.dialogs.standardize_dialog import StandardizeVideosDialog
    dlg = StandardizeVideosDialog()
    try:
        fmts = [dlg.convert_format.itemText(i) for i in range(dlg.convert_format.count())]
        assert any("Copy" in f or "Kopieren" in f for f in fmts), fmts
        res, fps, fmt = dlg.selected()
        assert "x" in res  # Aufloesung wie "1920x1080 (1080p)"
        assert "fps" in fps
        assert fmt  # nicht leer
    finally:
        dlg.deleteLater()

def test_b517_batch_convert_copy_codec_options(monkeypatch):
    # Mock duration check to avoid actual ffprobe calls
    monkeypatch.setattr("workers.import_export._ffprobe_duration", lambda path: 10.0)
    
    captured_cmds = []
    
    # Mock execution of ffmpeg to capture command arguments
    def mock_run_batch_ffmpeg(cmd, cancel_check, timeout, progress_cb=None):
        captured_cmds.append(cmd)
        mock_res = MagicMock()
        mock_res.returncode = 0
        return mock_res
        
    monkeypatch.setattr("workers.import_export._run_batch_ffmpeg_cancellable", mock_run_batch_ffmpeg)
    
    # Test case 1: vcodec = "copy"
    videos = [{"file_path": "test_video.mp4"}]
    worker = BatchConvertWorker(videos, "1920x1080", "30", "copy", ".mp4")
    # Mock path mkdir to do nothing and avoid system side effects
    monkeypatch.setattr("pathlib.Path.mkdir", lambda *args, **kwargs: None)
    
    worker._run_locked()
    
    assert len(captured_cmds) == 1
    cmd = captured_cmds[0]
    
    # Verify "-c:v copy" is in the command
    assert "-c:v" in cmd
    assert cmd[cmd.index("-c:v") + 1] == "copy"
    # Verify "-vf" is NOT in the command
    assert "-vf" not in cmd
    # Verify "-preset" is NOT in the command
    assert "-preset" not in cmd


def test_b517_batch_convert_preset_inclusion(monkeypatch):
    monkeypatch.setattr("workers.import_export._ffprobe_duration", lambda path: 10.0)
    monkeypatch.setattr("pathlib.Path.mkdir", lambda *args, **kwargs: None)
    
    captured_cmds = []
    def mock_run_batch_ffmpeg(cmd, cancel_check, timeout, progress_cb=None):
        captured_cmds.append(cmd)
        mock_res = MagicMock()
        mock_res.returncode = 0
        return mock_res
    monkeypatch.setattr("workers.import_export._run_batch_ffmpeg_cancellable", mock_run_batch_ffmpeg)
    
    videos = [{"file_path": "test_video.mp4"}]
    
    # x264 should have preset
    worker_x264 = BatchConvertWorker(videos, "1920x1080", "30", "libx264", ".mp4")
    worker_x264._run_locked()
    
    # prores should NOT have preset
    worker_prores = BatchConvertWorker(videos, "1920x1080", "30", "prores_ks", ".mov")
    worker_prores._run_locked()
    
    assert len(captured_cmds) == 2
    cmd_x264 = captured_cmds[0]
    cmd_prores = captured_cmds[1]
    
    assert "-preset" in cmd_x264
    assert cmd_x264[cmd_x264.index("-preset") + 1] == "medium"
    
    assert "-preset" not in cmd_prores


def test_b517_convert_controller_nvenc_mapping(monkeypatch):
    # Test mapping logic in convert controller
    from ui.controllers.convert import ConvertController
    
    # Mock window and UI elements
    mock_window = MagicMock()
    mock_window.convert_resolution.currentText.return_value = "1920x1080 (HD)"
    mock_window.convert_fps.currentText.return_value = "30 fps"
    
    # We mock get_all_video to return a dummy video list
    monkeypatch.setattr("services.ingest_service.get_all_video", lambda: [{"file_path": "test_video.mp4"}])
    
    # Mock task manager task creation by replacing the whole task_manager instance
    mock_task_manager = MagicMock()
    mock_task = MagicMock()
    mock_task.task_id = "test_task_id"
    mock_task_manager.create_task.return_value = mock_task
    monkeypatch.setattr("ui.controllers.convert.task_manager", mock_task_manager)
    
    created_workers = []
    # Mock BatchConvertWorker to capture arguments
    class MockBatchConvertWorker(QObject):
        finished = Signal(int, int)
        progress = Signal(int, str)
        error = Signal(str)
        
        def __init__(self, videos, resolution, fps, vcodec, ext):
            super().__init__()
            created_workers.append((videos, resolution, fps, vcodec, ext))
            self.task_id = None
            
        def run(self):
            pass
            
    # Swap out actual BatchConvertWorker constructor in convert controller
    monkeypatch.setattr("ui.controllers.convert.BatchConvertWorker", MockBatchConvertWorker)
    
    controller = ConvertController(mock_window)

    # B-525: Codec-Mapping wird ueber _run_standardize(res, fps, fmt) getestet
    # (das frueher inline-lesende _standardize_all_videos oeffnet jetzt einen
    # modalen Dialog und ist daher nicht headless aufrufbar).

    # Case A: MP4 H.264, NVENC available
    monkeypatch.setattr("services.convert_service.detect_nvenc", lambda: {"h264_nvenc": True})
    controller._run_standardize("1920x1080 (HD)", "30 fps", "MP4 (H.264)")
    assert len(created_workers) == 1
    assert created_workers[0][3] == "h264_nvenc"

    # Case B: MP4 H.264, NVENC NOT available
    created_workers.clear()
    monkeypatch.setattr("services.convert_service.detect_nvenc", lambda: {"h264_nvenc": False})
    controller._run_standardize("1920x1080 (HD)", "30 fps", "MP4 (H.264)")
    assert len(created_workers) == 1
    assert created_workers[0][3] == "libx264"

    # B-525 Case C: "Kopieren/Copy" -> vcodec "copy", ext ".mp4"
    created_workers.clear()
    controller._run_standardize("1920x1080 (HD)", "30 fps", "mp4 (Kopieren/Copy)")
    assert len(created_workers) == 1
    assert created_workers[0][3] == "copy"
    assert created_workers[0][4] == ".mp4"
