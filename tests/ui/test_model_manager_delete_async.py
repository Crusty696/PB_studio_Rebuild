"""Freeze-Fix: Model-Manager loescht Modelle asynchron (nicht im UI-Thread).

Verifizierter Bug: 52s-App-Freeze beim Model-Manager. Ursache-Analyse:
_on_delete_model / _on_delete_all_selected riefen delete_ollama_model
(bis 30s Timeout) bzw. delete_hf_model (KEIN Timeout, HF-Cache-Scan +
rmtree) SYNCHRON im UI-Thread. Jetzt via _DeleteWorker im QThread.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class _FakeSvc:
    def __init__(self):
        self.deleted = []

    def delete_ollama_model(self, mid):
        self.deleted.append(("ollama", mid))
        return True

    def delete_hf_model(self, mid):
        self.deleted.append(("hf", mid))
        return True


def test_delete_worker_deletes_all_targets(monkeypatch):
    _app()
    import services.model_lifecycle_service as mls
    from ui.dialogs.model_manager_dialog import _DeleteWorker

    fake = _FakeSvc()
    monkeypatch.setattr(mls, "get_model_lifecycle_service", lambda url: fake)

    captured = {}
    w = _DeleteWorker("http://x", [("m1", "ollama"), ("m2", "huggingface")])
    w.finished.connect(lambda d, e: captured.update(deleted=d, errors=e))
    w.run()  # synchron im Test — Signal feuert direkt

    assert captured["deleted"] == 2
    assert captured["errors"] == []
    assert ("ollama", "m1") in fake.deleted
    assert ("hf", "m2") in fake.deleted


def test_delete_worker_reports_errors_without_crashing(monkeypatch):
    _app()
    import services.model_lifecycle_service as mls
    from ui.dialogs.model_manager_dialog import _DeleteWorker

    class _Boom:
        def delete_ollama_model(self, mid):
            raise RuntimeError("ollama hängt")

        def delete_hf_model(self, mid):
            return False

    monkeypatch.setattr(mls, "get_model_lifecycle_service", lambda url: _Boom())

    captured = {}
    w = _DeleteWorker("http://x", [("m1", "ollama"), ("m2", "huggingface")])
    w.finished.connect(lambda d, e: captured.update(deleted=d, errors=e))
    w.run()

    # m1 wirft -> Fehler-Eintrag; m2 gibt False -> Fehler-Eintrag; kein Crash
    assert captured["deleted"] == 0
    assert len(captured["errors"]) == 2


def test_handlers_route_through_async_start_delete():
    """Quelltext-Vertrag: beide Loesch-Handler nutzen _start_delete
    (Worker-Thread), rufen NICHT mehr synchron delete_*_model im UI-Thread."""
    import inspect

    import ui.dialogs.model_manager_dialog as mm
    single = inspect.getsource(mm.ModelManagerDialog._on_delete_model)
    bulk = inspect.getsource(mm.ModelManagerDialog._on_delete_all_selected)
    assert "_start_delete" in single
    assert "_start_delete" in bulk
    # Kein synchroner Service-Abruf mehr im UI-Slot (das war der Freeze).
    assert "get_model_lifecycle_service" not in single
    assert "get_model_lifecycle_service" not in bulk


def test_start_delete_uses_qthread():
    import inspect

    import ui.dialogs.model_manager_dialog as mm
    src = inspect.getsource(mm.ModelManagerDialog._start_delete)
    assert "QThread()" in src
    assert "moveToThread" in src
