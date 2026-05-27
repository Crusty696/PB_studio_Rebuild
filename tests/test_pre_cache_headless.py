import sys
from unittest.mock import MagicMock, patch

# Minimale echte Dummy-Klassen für Qt-Objekte, um Metaklassenkonflikte bei Mocks zu verhindern
class DummyQObject:
    def __init__(self, *args, **kwargs):
        pass

class DummySignal:
    def __init__(self, *args, **kwargs):
        pass
    def connect(self, *args, **kwargs):
        pass

mock_qt_core = MagicMock()
mock_qt_core.QObject = DummyQObject
mock_qt_core.Signal = DummySignal

sys.modules["PySide6"] = MagicMock()
sys.modules["PySide6.QtCore"] = mock_qt_core
sys.modules["PySide6.QtGui"] = MagicMock()
sys.modules["PySide6.QtWidgets"] = MagicMock()

# Andere potenziell blockierende Audio-Module mocken
sys.modules["sounddevice"] = MagicMock()
sys.modules["soundfile"] = MagicMock()
sys.modules["librosa"] = MagicMock()

import pytest

# Test, ob der CLI-Handler in main.py `--pre-cache` korrekt und ohne Race-Condition abarbeitet
def test_pre_cache_headless_mode(monkeypatch):
    # Mocke sys.argv, damit `--pre-cache` übergeben wird
    monkeypatch.setattr(sys, "argv", ["main.py", "--pre-cache"])
    
    # Mocke ModelLifecycleService und get_model_lifecycle_service
    mock_service = MagicMock()
    mock_RECOMMENDED_HF_MODELS = [
        {"id": "google/siglip-so400m-patch14-384"}
    ]
    
    # Event, um das asynchrone Callback-Verhalten zu simulieren
    download_started_in_mock = False
    
    def mock_download_hf_model(m_id, progress_cb=None, revision="main"):
        # Simuliere asynchrones Setzen von downloading im Callback
        if progress_cb:
            class MockProgress:
                def __init__(self):
                    self.status = "downloading"
                    self.progress = 0.5
                    self.speed_mbps = 2.5
                    self.eta_sec = 10
                    self.finished = False
            
            # 1. downloading-Event abgeben
            progress_cb(MockProgress())
            
            # 2. finished-Event abgeben
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
         patch("services.model_lifecycle_service.RECOMMENDED_HF_MODELS", mock_RECOMMENDED_HF_MODELS), \
         patch("sys.exit") as mock_exit:
        
        # Importiere main und rufe auf
        import main
        main.main()
        
        # Sicherstellen, dass sys.exit(0) im CLI-Block aufgerufen wurde (als erster Aufruf vor dem restlichen Durchlauf)
        mock_exit.assert_any_call(0)
