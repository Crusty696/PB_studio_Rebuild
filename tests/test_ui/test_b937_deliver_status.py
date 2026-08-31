"""B-937 — die Statusleiste im DELIVER-Bereich stand dauerhaft auf demselben Text.

``StatusStrip.set_status`` (`ui/widgets/workflow_components.py:61`) hatte keinen
einzigen Aufrufer. Der Streifen zeigte deshalb immer "Export bereit, sobald eine
Timeline vorhanden ist." — waehrend eines Exports, nach Erfolg und nach
Fehlschlag. Weil ``export_log`` im derzeit unsichtbaren PROTOKOLL-Tab haengt
(B-933), war das die einzige Rueckmeldung, die den Nutzer haette erreichen
koennen.
"""

import pytest

from ui.controllers.export import ExportController


class _FakeStrip:
    def __init__(self):
        self.texte = []

    def set_status(self, text):
        self.texte.append(text)


class _FakeWindow:
    def __init__(self, mit_strip=True):
        self._deliver_ws = type("WS", (), {})()
        if mit_strip:
            self._deliver_ws.deliver_status = _FakeStrip()


def _controller(window):
    ctrl = ExportController.__new__(ExportController)
    ctrl.window = window
    return ctrl


def test_status_landet_im_streifen():
    win = _FakeWindow()
    _controller(win)._set_deliver_status("Export 42%: rendere")

    assert win._deliver_ws.deliver_status.texte == ["Export 42%: rendere"]


def test_ohne_streifen_kein_absturz():
    """Der Deliver-Bereich kann fehlen (Tests, fruehe Startphase)."""
    _controller(_FakeWindow(mit_strip=False))._set_deliver_status("egal")
    _controller(type("W", (), {})())._set_deliver_status("egal")


@pytest.mark.parametrize("methode", [
    "_start_export",
    "_on_export_progress",
    "_on_export_finished",
    "_on_export_error",
    "_start_preview_export",
    "_on_preview_progress",
    "_on_preview_finished",
    "_on_preview_error",
])
def test_jeder_zustandswechsel_meldet_sich(methode):
    """Quelltext-Guard: jeder Uebergang schreibt in die Statusleiste.

    Die Methoden brauchen ein komplettes PBWindow samt Workern und lassen sich
    hier nicht ausfuehren. Geprueft wird deshalb, dass der Aufruf im Rumpf
    steht — das haelt fest, dass kein Pfad wieder stumm wird.
    """
    import inspect

    src = inspect.getsource(getattr(ExportController, methode))
    assert "_set_deliver_status(" in src, f"{methode} meldet keinen Status"
