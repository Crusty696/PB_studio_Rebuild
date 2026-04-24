"""Bug C — UI Slow-Events: Regressionstests fuer den gepufferten Konsolen-Flush.

Sicherstellen, dass viele aufeinanderfolgende `_console_append`-Aufrufe NICHT
N synchrone QTextEdit.append()-Calls erzeugen, sondern in einem einzigen
Flush-Tick gebuendelt landen. Verhindert, dass per Worker-Progress-Tick die
Layout-Engine angeworfen wird (Resize / MetaCall SLOW EVENTs).
"""

from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QTextEdit, QTabWidget, QWidget

from ui.controllers.panel_setup import PanelSetupController


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _StubWindow(QWidget):
    """Minimaler PBWindow-Stub: ist ein QWidget (damit QTimer(self.window)
    in setup_console() einen gueltigen QObject-Parent bekommt) und hat ein
    QTabWidget als right_panel."""

    def __init__(self) -> None:
        super().__init__()
        self.right_panel = QTabWidget(self)


@pytest.fixture
def panel_setup() -> PanelSetupController:
    _ensure_qapp()
    win = _StubWindow()
    ps = PanelSetupController(win)  # type: ignore[arg-type]
    ps.setup_console()
    # Halte die Stub-Window-Referenz lebendig solange die Fixture lebt
    ps._test_win = win  # type: ignore[attr-defined]
    return ps


def test_console_append_buffers_into_single_flush(panel_setup: PanelSetupController) -> None:
    """1000 schnelle _console_append-Aufrufe duerfen NICHT 1000 widget-appends
    ergeben — sondern landen erst beim naechsten Flush in einem einzigen Block.
    """
    widget: QTextEdit = panel_setup.window.console_text  # type: ignore[attr-defined]

    # Widget-Append-Count messen via Block-Count vorher/nachher.
    blocks_before = widget.document().blockCount()

    t0 = time.perf_counter()
    for i in range(1000):
        panel_setup._console_append(f"[Test] line {i}")
    elapsed_append = time.perf_counter() - t0

    # Vor dem Flush: Buffer haelt alle 1000, Widget noch ~unveraendert
    # (das eine Init-"[System]"-Line ist evtl. schon drin)
    assert len(panel_setup._console_buffer) == 1000
    assert widget.document().blockCount() == blocks_before, (
        "Buffer-Append darf das Widget noch NICHT veraendert haben."
    )

    # Append-Phase muss schnell sein (kein synchroner UI-Update pro Call).
    assert elapsed_append < 0.2, (
        f"1000 _console_append-Aufrufe sollten < 200 ms dauern, "
        f"sind aber {elapsed_append * 1000:.0f} ms — Buffer greift nicht."
    )

    # Manueller Flush
    t1 = time.perf_counter()
    panel_setup._flush_console_buffer()
    elapsed_flush = time.perf_counter() - t1

    # Nach dem Flush: Buffer leer, Widget hat zusaetzliche Bloecke,
    # aber durch maxBlockCount=500 maximal 500 Total.
    assert panel_setup._console_buffer == []
    assert widget.document().blockCount() <= 500, (
        f"maxBlockCount muss greifen — aktuell {widget.document().blockCount()}."
    )

    # Flush selbst muss schnell sein — ein einziger Cursor-Insert + Trim.
    assert elapsed_flush < 0.5, (
        f"Flush 1000 Zeilen sollte < 500 ms dauern, ist {elapsed_flush * 1000:.0f} ms."
    )


def test_console_flush_is_idempotent_when_empty(panel_setup: PanelSetupController) -> None:
    """Ein Flush mit leerem Buffer darf das Widget nicht beruehren."""
    widget: QTextEdit = panel_setup.window.console_text  # type: ignore[attr-defined]
    blocks_before = widget.document().blockCount()
    panel_setup._flush_console_buffer()
    assert widget.document().blockCount() == blocks_before


def test_pbwindow_console_append_routes_through_buffer() -> None:
    """PBWindow._console_append muss durch den gepufferten Pfad routen,
    damit Worker-Progress-Lambdas nicht synchron das Widget anfassen."""
    _ensure_qapp()
    win = _StubWindow()
    ps = PanelSetupController(win)  # type: ignore[arg-type]
    ps.setup_console()

    # Faken eines minimalen PBWindow-Konstrukts: window-Stub mit panel_setup
    # und console_text gesetzt; dann die echte Methode aus main.py nachstellen.
    # Wir importieren die echte Methode, statt sie zu duplizieren.
    from main import PBWindow

    class _ProxyWin:
        panel_setup = ps
        console_text = ps.window.console_text  # type: ignore[attr-defined]

    proxy = _ProxyWin()
    PBWindow._console_append(proxy, "[Test] aus PBWindow-Pfad")  # type: ignore[arg-type]

    # Muss im Buffer landen, NICHT direkt im Widget.
    assert "[Test] aus PBWindow-Pfad" in ps._console_buffer
