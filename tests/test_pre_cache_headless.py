import sys
from unittest.mock import MagicMock, patch
import pytest

# Minimale echte Dummy-Klassen für Qt-Objekte, um Metaklassenkonflikte bei Mocks zu verhindern
class DummyQObject:
    def __init__(self, *args, **kwargs):
        pass

class DummySignal:
    def __init__(self, *args, **kwargs):
        pass
    def connect(self, *args, **kwargs):
        pass

# Test, ob der CLI-Handler in main.py `--pre-cache` korrekt und ohne Race-Condition abarbeitet
def test_pre_cache_headless_mode(monkeypatch):
    # Mocke sys.argv, damit `--pre-cache` übergeben wird
    monkeypatch.setattr(sys, "argv", ["main.py", "--pre-cache"])
    
    # Isoliertes Mocken von PySide6 und Audio-Modulen nur für diesen Testlauf
    mock_qt_core = MagicMock()
    mock_qt_core.QObject = DummyQObject
    mock_qt_core.Signal = DummySignal

    monkeypatch.setitem(sys.modules, "PySide6", MagicMock())
    monkeypatch.setitem(sys.modules, "PySide6.QtCore", mock_qt_core)
    monkeypatch.setitem(sys.modules, "PySide6.QtGui", MagicMock())
    monkeypatch.setitem(sys.modules, "PySide6.QtWidgets", MagicMock())
    monkeypatch.setitem(sys.modules, "sounddevice", MagicMock())
    monkeypatch.setitem(sys.modules, "soundfile", MagicMock())
    monkeypatch.setitem(sys.modules, "librosa", MagicMock())
    
    # Mocke ModelLifecycleService und get_model_lifecycle_service
    mock_service = MagicMock()
    mock_RECOMMENDED_HF_MODELS = [
        {"id": "google/siglip-so400m-patch14-384"}
    ]
    
    def mock_download_hf_model(m_id, progress_cb=None, revision="main"):
        if progress_cb:
            class MockProgress:
                def __init__(self):
                    self.status = "downloading"
                    self.progress = 0.5
                    self.speed_mbps = 2.5
                    self.eta_sec = 10
                    self.finished = False
            progress_cb(MockProgress())
            
            class MockProgressDone:
                def __init__(self):
                    self.status = "done"
                    self.progress = 1.0
                    self.speed_mbps = 0.0
                    self.eta_sec = 0
                    self.finished = True
            progress_cb(MockProgressDone())
        return True

    mock_service.download_hf_model = mock_download_hf_model
    
    # Patch main.py Importe und Methoden
    with patch("services.model_lifecycle_service.get_model_lifecycle_service", return_value=mock_service), \
         patch("services.model_lifecycle_service.RECOMMENDED_HF_MODELS", mock_RECOMMENDED_HF_MODELS):
        
        # Sicherstellen, dass main.py neu importiert wird, falls es bereits gecached war
        if "main" in sys.modules:
            del sys.modules["main"]
            
        import main
        with patch.object(
            main,
            "setup_logging",
            side_effect=AssertionError("--pre-cache darf nicht in GUI-Startup weiterlaufen"),
        ) as mock_setup_logging:
            with pytest.raises(SystemExit) as exit_info:
                main.main()

        assert exit_info.value.code == 0
        mock_setup_logging.assert_not_called()
