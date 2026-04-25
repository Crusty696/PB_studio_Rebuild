"""B-180: ChatDock-Watchdog gibt UI nach 60s wieder frei wenn Worker hängt.

Schutz gegen forever-frozen UI bei Ollama-Hang, Modell-Lazy-Load oder
toter TaskManager-Queue. Test verkürzt das Timeout auf 50ms damit der
Test in <1s durchläuft.
"""
from __future__ import annotations

import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from ui.chat_dock import ChatDock


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _wait_until(predicate, timeout_ms: int = 1000):
    """Spin-loop mit Qt-Event-Processing bis predicate True wird."""
    app = QApplication.instance()
    elapsed = 0
    step = 20
    while elapsed < timeout_ms:
        app.processEvents()
        if predicate():
            return True
        QTimer.singleShot(step, lambda: None)
        # blockierendes processEvents mit kurzer Wartezeit
        from PySide6.QtCore import QEventLoop, QTime
        loop = QEventLoop()
        QTimer.singleShot(step, loop.quit)
        loop.exec()
        elapsed += step
    return False


def test_watchdog_re_enables_ui_when_worker_hangs(qapp, monkeypatch):
    """Wenn der Worker `finished` nie emittiert, soll die UI nach Timeout
    wieder freigegeben sein und ein Fehler-Toast erscheinen.
    """
    dock = ChatDock()
    # Stub-Agent vermeidet echten Ollama-Call; wir simulieren das Hängen,
    # indem wir den Worker-Start abfangen.
    dock.set_agent(object())

    # Verhindern dass _on_send echten Worker startet — wir simulieren den
    # Pfad bis zur "Agent arbeitet..."-Zeile selbst.
    started = {"ok": False}

    original_on_send = dock._on_send

    def _intercept_on_send():
        # Setzt Input + Status wie der echte Pfad, aber ohne Worker zu starten
        dock.input_field.setText("test message")
        # Füge user-line hinzu
        dock.append_user("test message")
        dock.input_field.clear()
        dock.input_field.setEnabled(False)
        dock.btn_send.setEnabled(False)
        dock._status_cursor_pos = dock.chat_log.textCursor().position()
        dock._append_colored("Agent arbeitet...", "#888888")
        # Watchdog mit 50ms statt 60s
        dock._watchdog_timer = QTimer(dock)
        dock._watchdog_timer.setSingleShot(True)
        dock._watchdog_timer.timeout.connect(dock._on_agent_watchdog)
        dock._watchdog_timer.start(50)
        # Worker-Slot aber kein worker_run gestartet → simuliert hängen
        # Sentinel damit _on_agent_watchdog _worker is not None sieht
        class _FakeWorker:
            pass
        dock._worker = _FakeWorker()
        started["ok"] = True

    monkeypatch.setattr(dock, "_on_send", _intercept_on_send)

    dock._on_send()
    assert started["ok"]
    assert dock.input_field.isEnabled() is False
    assert dock.btn_send.isEnabled() is False

    # Warte bis Watchdog feuert
    ok = _wait_until(lambda: dock.input_field.isEnabled(), timeout_ms=2000)
    assert ok, "Watchdog hat UI nicht reaktiviert"
    assert dock.input_field.isEnabled() is True
    assert dock.btn_send.isEnabled() is True


