"""B-688: Schliesst der User den Setup-Wizard waehrend eines laufenden Downloads,
darf der QThread NICHT laufend zerstoert werden ("QThread: Destroyed while thread
is still running" -> nativer Crash 0xC0000409).

Der Fix beendet den Download-Thread ueber ``SetupWizard.done()`` /
``closeEvent`` -> ``_PageDownload.shutdown()``, bevor der Dialog verschwindet.
"""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


def _blocking_pull(started_flag):
    def fake_pull(self, model_name):
        started_flag["started"] = True
        # Kooperativ blockieren bis cancel() -> wie ein haengender Download.
        while not self._cancelled:
            time.sleep(0.005)
        return False, "Abgebrochen"
    return fake_pull


def test_done_stops_running_download_thread(monkeypatch):
    _qapp()
    import ui.dialogs.setup_wizard as sw

    flag = {"started": False}
    monkeypatch.setattr(sw._DownloadWorker, "_pull_ollama", _blocking_pull(flag))

    wiz = sw.SetupWizard()
    page = wiz._page_dl
    page.start(["fake-model"], [])

    # Warten bis der Worker-Thread wirklich laeuft.
    deadline = time.time() + 3.0
    while not flag["started"] and time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    assert flag["started"], "Download-Worker ist nicht angelaufen"
    assert page._thread is not None and page._thread.isRunning()

    thread = page._thread
    # Dialog schliessen (zentraler Ausgang) -> muss den Thread sauber beenden.
    wiz.done(0)

    assert not thread.isRunning(), "QThread laeuft nach Dialog-Close noch (Crash-Risiko)"
    assert page._thread is None


def test_shutdown_is_idempotent_without_download():
    _qapp()
    import ui.dialogs.setup_wizard as sw

    wiz = sw.SetupWizard()
    # Nie gestartet -> shutdown darf nicht crashen.
    wiz._page_dl.shutdown()
    wiz.done(0)  # zweiter Weg, ebenfalls no-op
