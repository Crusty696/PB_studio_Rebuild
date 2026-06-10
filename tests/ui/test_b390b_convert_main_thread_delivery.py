"""B-390 (Folgebug): Convert-DB-Job-Ergebnisse muessen den Main-Thread erreichen.

Die Effekt-Combo blieb leer, obwohl die Timeline 767 Eintraege hatte:
``_refresh_effects_combos`` laedt im convert_db-ThreadPoolExecutor (kein Qt-Event-
Loop) und lieferte das Ergebnis per ``QTimer.singleShot`` — das aus einem Nicht-Qt-
Thread NIE feuert. Fix: ein QObject-Invoker (Qt-Signal, queued an den Main-Thread).
"""

from __future__ import annotations

import inspect
import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


def test_invoker_delivers_callback_from_worker_thread():
    _qapp()
    from ui.controllers.convert import _MainThreadInvoker

    inv = _MainThreadInvoker()
    ran = []
    t = threading.Thread(target=lambda: inv.post(lambda: ran.append("ok")))
    t.start()
    t.join()

    deadline = time.monotonic() + 2.0
    while not ran and time.monotonic() < deadline:
        _qapp().processEvents()
        time.sleep(0.01)

    assert ran == ["ok"], "Invoker lieferte den Worker-Callback nicht in den Main-Thread"


def test_b390b_fetch_closures_use_invoker_not_qtimer():
    """Die convert_db-Pool-Pfade liefern via _main_invoker.post, nicht QTimer.singleShot."""
    import ui.controllers.convert as conv
    for name in ("_refresh_effects_combos", "_on_effects_clip_changed", "_show_effect_preview"):
        src = inspect.getsource(getattr(conv.ConvertController, name))
        assert "_main_invoker.post" in src, f"{name} nutzt den Main-Thread-Invoker nicht"
        # Call-Pattern (mit Klammer) — der erklaerende Kommentar nennt den Namen ohne Klammer.
        assert "QTimer.singleShot(" not in src, (
            f"{name} nutzt noch QTimer.singleShot() (feuert aus dem Pool-Thread nie)"
        )
