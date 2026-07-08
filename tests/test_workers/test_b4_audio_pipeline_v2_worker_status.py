import pytest
from unittest.mock import MagicMock, patch
from workers.audio_pipeline_v2_worker import AudioPipelineV2Worker
from services.analysis_status_service import get_status

def test_audio_pipeline_v2_worker_status_writes(tmp_path):
    """B4 (DB-006): Verifiziert, dass der AudioPipelineV2Worker beim Durchlaufen
    der Pipeline den Status in die DB schreibt."""
    
    # Mocking orchestrator/stages to bypass heavy DL models
    mock_stage = MagicMock()
    mock_stage.name = "beat_grid"
    
    # Simuliert erfolgreichen Run der Stage
    def run_mock(ctx):
        ctx.set_result("beat_grid", {"bpm": 128.0})
    mock_stage.run = run_mock
    
    with patch("services.audio_pipeline.stages.build_default_stages", return_value=[mock_stage]):
        worker = AudioPipelineV2Worker(audio_track_id=997, file_path="dummy_v2.mp3")
        
        # Started/Finished signals tracken
        started_called = []
        finished_called = []
        
        worker.progress.connect(lambda pct, msg: started_called.append((pct, msg)))
        worker.finished.connect(lambda tid, res: finished_called.append((tid, res)))
        
        # Ausführen
        worker.run()
        
        # Assertions
        assert len(finished_called) == 1
        
        # Check DB status
        status = get_status("audio", 997)
        assert "bpm_detection" in status
        assert status["bpm_detection"].status == "done"
        assert status["bpm_detection"].value_summary.get("bpm") == 128.0
