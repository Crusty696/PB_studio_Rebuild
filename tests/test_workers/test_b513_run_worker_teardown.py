import pytest
import shiboken6
from PySide6.QtCore import QObject, Signal, QThread
from workers.base import run_worker, BaseWorker

class DummyWorker(QObject):
    finished = Signal(object)
    error = Signal(str)
    
    def __init__(self):
        super().__init__()
        self._cancelled = False
        self._errored = False
        
    def cancel(self):
        self._cancelled = True
        
    def run(self):
        pass

def test_run_worker_owner_destruction(qapp):
    owner = QObject()
    worker = DummyWorker()
    
    thread = run_worker(owner, worker)
    
    assert thread is not None
    assert isinstance(thread, QThread)
    
    # C++ Instanz von owner direkt zerstoeren (emittiert destroyed und macht isValid=False)
    shiboken6.delete(owner)
    qapp.processEvents()
    
    # Verifizieren, dass worker.cancel() aufgerufen wurde
    assert worker._cancelled is True
    
    # Cleanup
    thread.quit()
    thread.wait()

def test_run_worker_callback_guarded_after_owner_destruction(qapp):
    owner = QObject()
    worker = DummyWorker()
    
    calls = []
    def on_finish(payload):
        calls.append(payload)
        
    thread = run_worker(owner, worker, on_finish=on_finish)
    
    # C++ Instanz loeschen
    shiboken6.delete(owner)
    qapp.processEvents()
    
    # finished emittieren nach owner-zerstoerung
    worker.finished.emit("payload")
    qapp.processEvents()
    
    # Callback darf nicht aufgerufen worden sein, da der owner geloescht wurde
    assert len(calls) == 0
    
    # Cleanup
    thread.quit()
    thread.wait()
