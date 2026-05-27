import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

# Test, ob start_pb_studio.py die Pfade nach einem automatischen Setup korrekt re-evaluiert
def test_start_script_re_resolves_paths_after_setup(monkeypatch):
    import start_pb_studio
    
    # Mocke resolve_venv_paths, um beim ersten Aufruf eine nicht existierende Umgebung zurückzugeben,
    # und nach dem Setup die korrekte (existierende) Umgebung
    call_count = 0
    dummy_venv_dir = Path("dummy_venv")
    
    def mock_resolve_venv_paths():
        nonlocal call_count
        call_count += 1
        # existierende Umgebung zurückgeben
        p = MagicMock()
        p.exists.return_value = True
        return dummy_venv_dir, p
            
    monkeypatch.setattr(start_pb_studio, "resolve_venv_paths", mock_resolve_venv_paths)
    
    # Mocke globaler Zustand
    start_pb_studio.VENV_DIR = dummy_venv_dir
    start_pb_studio.VENV_PYTHON = MagicMock()
    start_pb_studio.VENV_PYTHON.exists.return_value = False # Anfangs nicht existierend
    
    # Mocke subprocess.run, um das Setup-Skript und den anschließenden Python-Check erfolgreich zu simulieren
    mock_run = MagicMock()
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = "Python 3.10.12"
    
    # Mocke Path.exists so, dass MAIN_PY und setup_script existieren
    real_exists = Path.exists
    def mock_path_exists(self):
        if "main.py" in str(self) or "setup_pb_studio.py" in str(self):
            return True
        return real_exists(self)
        
    with patch("subprocess.run", mock_run), \
         patch("sys.exit") as mock_exit, \
         patch("shutil.rmtree"), \
         patch("builtins.input") as mock_input, \
         patch.object(Path, "exists", mock_path_exists):
         
        # Rufe main() auf
        start_pb_studio.main()
        
        # Verifiziere, dass resolve_venv_paths nach dem Setup genau einmal aufgerufen wurde
        assert call_count == 1
        
        # Verifiziere, dass subprocess.run das Setup-Skript aufgerufen hat
        setup_call = any("setup_pb_studio.py" in str(arg) for call in mock_run.call_args_list for arg in call[0][0])
        assert setup_call
        
        # Verifiziere, dass kein sys.exit(1) wegen Setup-Fehlern aufgerufen wurde
        mock_exit.assert_not_called()
