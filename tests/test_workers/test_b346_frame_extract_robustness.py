"""B-346 (F-14): FrameExtractWorker Robustness Test.

Verifiziert, dass MemoryError, RuntimeError und andere Ausnahmen im FrameExtractWorker
abgefangen werden, das `error`-Signal senden und schließlich das `finished`-Signal emittieren,
damit der GlobalTaskManager den Thread sauber beenden kann.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import subprocess
from PySide6.QtWidgets import QApplication
from workers.video import FrameExtractWorker


def _qapp():
    return QApplication.instance() or QApplication([])


def test_frame_extract_worker_handles_runtime_error(monkeypatch):
    _qapp()
    worker = FrameExtractWorker("test.mp4", 1.0, 320, 180)
    
    def fake_run_raise_runtime(*args, **kwargs):
        raise RuntimeError("Fake OOM or engine crash")
        
    monkeypatch.setattr(subprocess, "run", fake_run_raise_runtime)
    
    errors = []
    finished_called = []
    
    worker.error.connect(lambda msg: errors.append(msg))
    worker.finished.connect(lambda: finished_called.append(True))
    
    worker.run()
    
    assert worker._errored is True
    assert len(errors) == 1
    assert "Fake OOM or engine crash" in errors[0]
    assert len(finished_called) == 1


def test_frame_extract_worker_handles_memory_error(monkeypatch):
    _qapp()
    worker = FrameExtractWorker("test.mp4", 1.0, 320, 180)
    
    def fake_run_raise_memory(*args, **kwargs):
        raise MemoryError("Out of memory mock")
        
    monkeypatch.setattr(subprocess, "run", fake_run_raise_memory)
    
    errors = []
    finished_called = []
    
    worker.error.connect(lambda msg: errors.append(msg))
    worker.finished.connect(lambda: finished_called.append(True))
    
    worker.run()
    
    assert worker._errored is True
    assert len(errors) == 1
    assert "Out of memory mock" in errors[0]
    assert len(finished_called) == 1
