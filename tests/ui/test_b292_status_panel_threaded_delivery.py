"""B-292: Das Analyse-Status-Panel muss die im Hintergrund geladenen Steps
tatsaechlich in der Tabelle anzeigen.

Bug: ``refresh()`` laedt den Status in einem ``ThreadPoolExecutor``-Worker
(kein Qt-Event-Loop) und lieferte das Ergebnis per ``QTimer.singleShot`` an den
Main-Thread. Ein aus einem Nicht-Qt-Thread gestarteter QTimer feuert nie -> das
UI-Update lief nie -> Tabelle blieb LEER, obwohl die DB done-Steps hat.

Dieser Test setzt ein Media mit 9 "done"-Steps (gemockt) und erwartet, dass die
Tabelle danach Zeilen hat.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


def _fake_status_dict():
    import services.analysis_status_service as svc
    return {
        step: SimpleNamespace(status="done", value_summary={}, error_message=None,
                              step_key=step)
        for step in svc.VIDEO_STEPS
    }


def test_b292_panel_populates_table_from_background_load(monkeypatch):
    _qapp()
    import ui.widgets.analysis_status_panel as panel_mod
    import services.analysis_status_service as svc

    monkeypatch.setattr(panel_mod.analysis_status_service, "infer_from_db",
                        lambda *a, **k: None)
    monkeypatch.setattr(panel_mod.analysis_status_service, "get_status",
                        lambda *a, **k: _fake_status_dict())

    panel = panel_mod.AnalysisStatusPanel()
    panel.set_media("video", 1)

    # Warte auf den Background-Load + Main-Thread-Delivery (max ~3s).
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and panel.table.rowCount() == 0:
        _qapp().processEvents()
        time.sleep(0.02)

    assert panel.table.rowCount() == len(svc.VIDEO_STEPS), (
        f"B-292: Status-Tabelle blieb leer (rowCount={panel.table.rowCount()}) "
        "trotz 9 done-Steps — Background-Delivery erreicht den Main-Thread nicht."
    )
