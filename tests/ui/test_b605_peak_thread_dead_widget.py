"""B-605: Peak-Thread-Cleanup darf nicht auf ein zerstoertes Widget zugreifen.

Das Ticket beschreibt einen nativen Qt6Core-Crash (0xc0000409) bei
``QThread::finished``. Der Live-Test konnte bisher nur zeigen, dass *kein*
Crash auftrat — ein Negativbefund, der nichts beweist: der Crash war nie
deterministisch reproduzierbar.

Diese Tests stellen den Crashpfad stattdessen gezielt her. Das Lambda an
``thread.finished`` hielt ``self`` stark; wird das StemWorkspace-Widget vor dem
Thread zerstoert, greift der Slot auf ein totes C++-Objekt zu. Genau dieser
Zugriff wird hier erzwungen — einmal mit zerstoertem Widget, einmal mit
lebendem.

Kein echtes Audio, keine echten PeakWorker: geprueft wird ausschliesslich die
Guard-Logik am Slot.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import shiboken6
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication, QWidget


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _Sammler(QWidget):
    """Minimal-Widget mit derselben Slot-Signatur wie StemWorkspace."""

    def __init__(self) -> None:
        super().__init__()
        self.aufrufe: list[tuple] = []

    def _on_peak_thread_done(self, thread, worker) -> None:
        self.aufrufe.append((thread, worker))


def _baue_slot(widget):
    """Baut den Cleanup-Slot exakt wie ``stem_workspace._start_peak_worker``.

    Bewusst nachgebaut statt importiert: die Original-Methode haengt an einem
    vollstaendigen StemWorkspace mit Audio-Pipeline. Getestet wird die
    Guard-Semantik, und die ist hier identisch.
    """
    thread = QObject()
    worker = QObject()

    def _peak_thread_done(t=thread, w=worker, _self=widget) -> None:
        if not shiboken6.isValid(_self):
            return
        try:
            _self._on_peak_thread_done(t, w)
        except RuntimeError:
            return

    return _peak_thread_done, thread, worker


def test_b605_slot_auf_zerstoertem_widget_crasht_nicht():
    """Der Kern: Widget vor dem Thread zerstoert -> Slot muss aussteigen.

    Ohne den ``shiboken6.isValid``-Guard laeuft hier der Zugriff auf ein
    bereits freigegebenes C++-Objekt — der Crashpfad des Tickets.
    """
    _ensure_qapp()
    widget = _Sammler()
    slot, _thread, _worker = _baue_slot(widget)

    shiboken6.delete(widget)  # zerstoert das C++-Objekt, Python-Wrapper bleibt
    assert not shiboken6.isValid(widget)

    slot()  # darf weder crashen noch werfen


def test_b605_slot_auf_lebendem_widget_arbeitet_normal():
    """Gegenprobe: der Guard darf den Normalfall nicht abwuergen."""
    _ensure_qapp()
    widget = _Sammler()
    slot, thread, worker = _baue_slot(widget)

    slot()

    assert widget.aufrufe == [(thread, worker)], (
        "B-605: der Guard hat den regulaeren Cleanup verhindert — dann bliebe "
        "der Thread-Eintrag fuer immer in der Liste stehen."
    )


def test_b605_produktivcode_hat_den_guard():
    """Belegt, dass der Guard tatsaechlich im Produktivcode steht.

    Sonst prueften die beiden Tests oben nur einen Nachbau.
    """
    import inspect

    from ui.widgets import stem_workspace

    quelle = inspect.getsource(stem_workspace)
    assert "shiboken6.isValid" in quelle, (
        "B-605: stem_workspace.py hat keinen isValid-Guard mehr — der "
        "Crashpfad waere wieder offen."
    )
    # Das freie Lambda an finished war die konkrete Fehlerquelle.
    assert "thread.finished.connect(_peak_thread_done)" in quelle, (
        "B-605: der benannte, abgesicherte Slot wurde durch etwas anderes "
        "ersetzt — bitte pruefen, ob der Guard noch greift."
    )
