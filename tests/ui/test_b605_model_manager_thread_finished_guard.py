"""B-605: QThread::finished-Slot darf nicht auf ein zerstoertes C++-Widget
schreiben (Null-Pointer-Write in Qt6Core!qt_static_metacall).

Root-Cause-Klasse (Code-Review 2026-07-16, aus dem B-605-Crashdump-Muster
abgeleitet): ein freies Lambda auf ``thread.finished`` hat KEINEN QObject-
Receiver. Qt kann eine solche Verbindung nicht automatisch trennen, wenn das
umgebende QObject (hier der ModelManagerDialog) zerstoert wird. Blockiert ein
Scan-/Status-Worker im ``closeEvent`` laenger als das dortige 1s-``wait()``-
Timeout (z.B. HTTP-Hang zu Ollama), wird der Dialog zerstoert, das Lambda
feuert danach trotzdem und schreibt auf den freigegebenen ``_refresh_btn``.

Fix: gebundene Methode (``_on_scan_thread_finished``) statt Lambda -> Qt gibt
``self`` als Receiver und trennt die Verbindung automatisch bei Dialog-
Zerstoerung; plus ``shiboken6.isValid``-Guard als zweites Netz.

Hinweis zur Ehrlichkeit: Der originale B-605-Crashdump (2026-07-08) enthielt
keine Python-Frames -> es ist NICHT bewiesen, dass genau diese Stelle der
damalige Crash war. Dies ist ein verifiziertes LATENTES Vorkommen desselben
Musters, kein bewiesener Fix des Original-Crashs.
"""
import inspect
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import shiboken6
from PySide6.QtWidgets import QApplication, QPushButton


def _app():
    return QApplication.instance() or QApplication([])


def _make_dialog():
    from ui.dialogs.model_manager_dialog import ModelManagerDialog
    # QTimer.singleShot(100, _start_scan) im __init__ feuert erst bei
    # processEvents nach 100ms — die Tests verarbeiten keine solchen Events,
    # also startet kein echter Scan/Netzwerk.
    return ModelManagerDialog(parent=None, ollama_url="http://localhost:1")


def test_scan_thread_finished_connects_bound_method_not_lambda():
    """Regressions-Pin: _start_scan darf thread.finished NICHT an ein Lambda
    haengen (kein Receiver -> kein Auto-Disconnect). Bound method Pflicht."""
    from ui.dialogs.model_manager_dialog import ModelManagerDialog

    src = inspect.getsource(ModelManagerDialog._start_scan)
    assert "_scan_thread.finished.connect(self._on_scan_thread_finished)" in src, (
        "B-605: _scan_thread.finished muss an die gebundene Methode "
        "_on_scan_thread_finished haengen (Auto-Disconnect bei Dialog-Zerstoerung)."
    )
    assert "_scan_thread.finished.connect(lambda" not in src, (
        "B-605: Lambda auf _scan_thread.finished ist verboten (kein Receiver)."
    )


def test_on_scan_thread_finished_enables_button_when_valid():
    _app()
    dlg = _make_dialog()
    try:
        # B-651: _on_scan_thread_finished ruft _check_ollama_status, das einen
        # ECHTEN Status-QThread (HTTP) startet. Der ueberlebte den Test-Teardown
        # -> "QThread: Destroyed while thread is still running" -> 0xC0000409
        # (toetete den ganzen pytest-Prozess ohne Summary). Unit-Scope hier ist
        # NUR das Button-Re-Enable -> Status-Check stubben, kein echter Thread.
        dlg._check_ollama_status = lambda: None
        dlg._refresh_btn.setEnabled(False)
        dlg._on_scan_thread_finished()
        assert dlg._refresh_btn.isEnabled() is True
    finally:
        dlg.close()
        dlg.deleteLater()
        _app().processEvents()


def test_on_scan_thread_finished_survives_deleted_button():
    """Kernfall: wird _refresh_btn (C++) zerstoert bevor der Slot feuert,
    darf _on_scan_thread_finished NICHT crashen (shiboken-Guard)."""
    _app()
    dlg = _make_dialog()
    try:
        dlg._check_ollama_status = lambda: None  # B-651: kein echter Thread
        btn = dlg._refresh_btn
        assert isinstance(btn, QPushButton)
        # C++-Button hart zerstoeren (simuliert Dialog-Teil-Teardown).
        shiboken6.delete(btn)
        _app().processEvents()
        assert not shiboken6.isValid(btn)
        # Darf nicht raisen (frueher: Zugriff auf freigegebenes Qt-Objekt).
        dlg._on_scan_thread_finished()
    finally:
        # B-651: siehe oben — Status-QThread via close() sauber beenden.
        dlg.close()
        dlg.deleteLater()
        _app().processEvents()
