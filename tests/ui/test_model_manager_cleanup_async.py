"""Freeze-Fix: Model-Manager Cleanup-Analyse laeuft async (nicht im UI-Thread).

get_cleanup_candidates liest die Registry-DB; formal synchron konnte das den
UI-Thread bis DB_BUSY_TIMEOUT (30s) blockieren. Jetzt via _CleanupScanWorker.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_cleanup_worker_returns_candidates(monkeypatch):
    _app()
    import services.model_lifecycle_service as mls
    from ui.dialogs.model_manager_dialog import _CleanupScanWorker

    class _Svc:
        def get_cleanup_candidates(self, days_unused):
            assert days_unused == 42
            return ["c1", "c2"]

    monkeypatch.setattr(mls, "get_model_lifecycle_service", lambda url: _Svc())

    captured = {}
    w = _CleanupScanWorker("http://x", 42)
    w.finished.connect(lambda c: captured.update(cands=c))
    w.run()
    assert captured["cands"] == ["c1", "c2"]


def test_cleanup_worker_survives_service_error(monkeypatch):
    _app()
    import services.model_lifecycle_service as mls
    from ui.dialogs.model_manager_dialog import _CleanupScanWorker

    def boom(url):
        raise RuntimeError("db weg")

    monkeypatch.setattr(mls, "get_model_lifecycle_service", boom)
    captured = {}
    w = _CleanupScanWorker("http://x", 30)
    w.finished.connect(lambda c: captured.update(cands=c))
    w.run()  # darf nicht crashen -> leere Liste
    assert captured["cands"] == []


def test_cleanup_scan_uses_qthread():
    import inspect

    import ui.dialogs.model_manager_dialog as mm
    src = inspect.getsource(mm.ModelManagerDialog._on_cleanup_scan)
    assert "QThread()" in src
    assert "moveToThread" in src
    # kein synchroner Service-Abruf mehr im UI-Slot (Worker macht den DB-Call)
    assert "get_model_lifecycle_service" not in src
    assert "_CleanupScanWorker" in src
