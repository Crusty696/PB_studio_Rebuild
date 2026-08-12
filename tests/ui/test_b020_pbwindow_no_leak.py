"""B-020 Regressionstest: PBWindow darf nach close() nicht weiterleben.

Gemessener Befund (2026-08-12, gegen `main` @ 3397043): nach ``close()``
zerstoert Qt das C++-Fenster korrekt, der **Python-Wrapper samt Objektbaum**
lebte aber weiter (6/6 Zyklen). Haltende Referenz war ein reiner
Python-Zyklus

    PBWindow.__dict__ -> 13 Controller -> controller.window     -> PBWindow
                      -> ChatDock      -> ChatDock._main_window -> PBWindow

den der GC nicht abraeumt. Fix: die Rueckwaertskanten sind ``weakref``
(``ui/base_component.py``, ``ui/chat_dock.py``).

Der End-to-End-Nachweis laeuft in einem **Subprozess**. Grund: im
pytest-Prozess halten Fixture-/Assertion-Machinerie und Log-Capture zusaetzliche
Referenzen auf das Fenster, dann misst man nicht den Fix, sondern pytest.
Zwei weitere Fallstricke sind im Messkript beruecksichtigt:
1. ``deleteLater()`` ohne ``sendPostedEvents(None, DeferredDelete)`` wird nie
   zugestellt.
2. ``close()`` blockiert offscreen an der modalen ``QMessageBox.question``
   ("Task(s) laufen noch") in ``main.py``.
"""
import gc
import os
import subprocess
import sys
import textwrap
import weakref
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

REPO_ROOT = Path(__file__).resolve().parents[2]

_MEASURE_SRC = textwrap.dedent(
    """
    import gc, os, sys, weakref
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ.setdefault("PYTEST_CURRENT_TEST", "b020 (call)")
    sys.path.insert(0, sys.argv[1])

    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtCore import QCoreApplication, QEvent

    app = QApplication.instance() or QApplication([])
    # Offscreen klickt niemand — modale Dialoge im closeEvent bejahen.
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)

    from main import PBWindow

    alive = 0
    for _ in range(int(sys.argv[2])):
        win = PBWindow()
        ref = weakref.ref(win)
        app.processEvents()
        win.close()
        win.deleteLater()
        del win
        for _ in range(12):
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
            gc.collect()
        if ref() is not None:
            alive += 1
    print("PB_ALIVE=%d" % alive)
    """
)


@pytest.mark.slow
def test_pbwindow_is_released_after_close(tmp_path):
    script = tmp_path / "b020_measure.py"
    script.write_text(_MEASURE_SRC, encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(script), str(REPO_ROOT), "2"],
        capture_output=True,
        text=True,
        timeout=900,
        cwd=str(REPO_ROOT),
    )
    marker = [l for l in proc.stdout.splitlines() if l.startswith("PB_ALIVE=")]
    assert marker, f"Messkript lieferte kein Ergebnis.\nSTDOUT:\n{proc.stdout[-3000:]}\nSTDERR:\n{proc.stderr[-3000:]}"
    alive = int(marker[-1].split("=", 1)[1])

    assert alive == 0, (
        f"B-020: {alive} PBWindow-Wrapper leben nach close()+DeferredDelete weiter — "
        "die Rueckwaertskante Controller/ChatDock -> PBWindow ist wieder stark."
    )


def test_controller_backedge_is_weak():
    """Strukturgarantie: die Rueckwaertskante haelt das Fenster nicht am Leben."""
    from PySide6.QtWidgets import QMainWindow

    from ui.base_component import PBComponent

    QApplication.instance() or QApplication([])
    win = QMainWindow()
    comp = PBComponent(win)
    assert comp.window is win

    ref = weakref.ref(win)
    del win
    gc.collect()

    assert ref() is None, "B-020: Controller haelt das Fenster stark fest."
    assert comp.window is None
    assert comp._window_alive() is False


def test_chatdock_backedge_is_weak():
    """Prueft den ChatDock-Deskriptor ohne echtes QDockWidget.

    Ein parentloses ``ChatDock`` in einem pytest-Prozess zu konstruieren und
    wieder abzuraeumen liess den Interpreter abstuerzen (Qt-Teardown-Reihenfolge),
    deshalb wird der Property-Deskriptor an einer Stellvertreter-Klasse getestet.
    Der End-to-End-Fall ist vom Subprozess-Test oben abgedeckt.
    """
    from PySide6.QtWidgets import QMainWindow

    from ui.chat_dock import ChatDock

    descriptor = ChatDock.__dict__["_main_window"]
    assert isinstance(descriptor, property)

    class _Probe:
        _main_window = descriptor

    QApplication.instance() or QApplication([])
    probe = _Probe()
    win = QMainWindow()
    probe._main_window = win
    assert probe._main_window is win

    ref = weakref.ref(win)
    del win
    gc.collect()

    assert ref() is None, "B-020: ChatDock haelt das Fenster stark fest."
    assert probe._main_window is None


def test_non_qobject_window_stays_strong():
    """Test-Doubles haben keinen anderen Besitzer und muessen stark bleiben."""
    from types import SimpleNamespace

    from ui.base_component import PBComponent

    comp = PBComponent(SimpleNamespace(logger=None))
    assert comp.window is not None
    assert comp._window_alive() is True
