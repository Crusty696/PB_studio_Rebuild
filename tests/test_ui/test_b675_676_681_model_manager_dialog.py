"""B-675/676/681: Thread-Lebenszyklus im Model-Manager-Dialog.

Die Tests laufen bewusst OHNE echte Worker-Threads (``QThread.start`` wird
no-op'd) — die realen Worker machen blockierende HTTP-Calls, und ein echter
Lauf waere sowohl nichtdeterministisch als auch (Lesson 1677bac2) nativ-crash-
gefaehrdet. Geprueft werden die Verdrahtungs-Invarianten, nicht die HTTP-Logik.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QThread
from PySide6.QtGui import QCloseEvent

import ui.dialogs.model_manager_dialog as mmd
from ui.dialogs.model_manager_dialog import ModelManagerDialog


@pytest.fixture(autouse=True)
def _no_real_threads(monkeypatch):
    """Kein echter Worker-Thread darf starten."""
    monkeypatch.setattr(QThread, "start", lambda self, *a, **k: None)


def _make_dialog(qtbot):
    d = ModelManagerDialog()
    qtbot.addWidget(d)
    return d


def test_b681_status_quit_targets_own_thread_not_rebound(qtbot, monkeypatch):
    """B-681: kehrt ein alter Status-Worker zurueck, nachdem ein spaeterer
    _check_ollama_status ``self._status_thread`` neu gebunden hat, muss er
    SEINEN eigenen Thread quitten — nicht den frisch gebundenen."""
    quit_calls = []

    class _CountingThread(QThread):
        def quit(self):
            quit_calls.append(self)
            super().quit()

    monkeypatch.setattr(mmd, "QThread", _CountingThread)
    d = _make_dialog(qtbot)

    d._check_ollama_status()
    thread_a, worker_a = d._status_thread, d._status_worker
    d._check_ollama_status()
    thread_b = d._status_thread

    assert thread_a is not thread_b, "zweiter Aufruf muss neu binden"

    worker_a.success.emit("1.0")

    assert thread_a in quit_calls, "alter Worker muss seinen eigenen Thread quitten"
    assert thread_b not in quit_calls, "der frisch gebundene Thread darf NICHT gequittet werden"


def test_b676_closeevent_parks_running_thread(qtbot):
    """B-676: ein noch laufender Thread (wait timeout) darf im closeEvent NICHT
    deleteLater'd werden (0xC0000409), sondern muss geparkt werden."""
    deleted = []

    class _FakeRunning(QThread):
        def isRunning(self):
            return True

        def wait(self, msecs=0):
            return False  # simuliert blockierenden Worker -> wait laeuft ab

        def deleteLater(self):
            deleted.append(self)

    d = _make_dialog(qtbot)
    fr = _FakeRunning()
    d._delete_thread = fr
    d._scan_thread = None
    d._status_thread = None
    d._cleanup_thread = None
    d._download_threads = {}

    d.closeEvent(QCloseEvent())

    assert fr in d._dying_threads, "laufender Thread muss geparkt werden"
    assert fr not in deleted, "deleteLater darf nicht auf einem laufenden Thread aufgerufen werden"


def test_b676_closeevent_deletes_finished_thread(qtbot):
    """Gegenprobe: ein bereits beendeter Thread wird sauber deleteLater'd."""
    deleted = []

    class _FakeFinished(QThread):
        def isRunning(self):
            return False

        def deleteLater(self):
            deleted.append(self)

    d = _make_dialog(qtbot)
    ff = _FakeFinished()
    d._delete_thread = ff
    d._scan_thread = None
    d._status_thread = None
    d._cleanup_thread = None
    d._download_threads = {}

    d.closeEvent(QCloseEvent())

    assert ff in deleted, "beendeter Thread soll deleteLater'd werden"
    assert ff not in getattr(d, "_dying_threads", []), "beendeter Thread nicht parken"


def test_b675_download_uses_bound_slots_and_cleans_up(qtbot):
    """B-675: der Download verdrahtet gebundene Slots (kein freies Lambda) und
    legt den Kontext am Worker ab; das gebundene finished raeumt sauber auf."""
    d = _make_dialog(qtbot)

    d._start_download("mymodel", "ollama")
    worker = d._download_workers["mymodel"]

    # Kontext am Worker statt in einer Lambda-Closure ueber den Dialog:
    assert getattr(worker, "_pb_model_id", None) == "mymodel"
    assert getattr(worker, "_pb_row_widget", None) is not None

    # finished -> gebundener Slot -> _on_download_finished raeumt die Dicts.
    worker.finished.emit(True)
    qtbot.wait(50)  # QueuedConnection abarbeiten

    assert "mymodel" not in d._download_workers
    assert "mymodel" not in d._download_threads
