"""B-918 und B-925 — zwei Stellen, an denen ein Klick zu viel Arbeit ausloest.

**B-918:** ``_on_test_clicked`` deaktiviert nur ``_btn_test``. Der
Refresh-Knopf blieb bedienbar und rief dieselbe Methode erneut auf — dabei
wurden ``_test_thread`` und ``_test_worker`` ueberschrieben, und der erste
Thread lief ohne Referenz weiter.

**B-925:** Die Entprellung fasste 200 ms zusammen. Die Proxy-Konvertierungen
meldeten sich im Sekundentakt fertig, also lief pro Datei ein eigenes
"Medien-DB laden" — bei 121 Videos 121 Ladevorgaenge. Zwei Aufrufer speisen
dieselbe Stelle, deshalb sitzt die Bremse in der Entprellung selbst.
"""

from __future__ import annotations

import inspect

import pytest


# ── B-918 ────────────────────────────────────────────────────────────────────

class _Thread:
    def __init__(self, laeuft: bool):
        self._laeuft = laeuft

    def isRunning(self) -> bool:
        return self._laeuft


class _Dialog:
    """Nur die Teile, die `_test_laeuft` und `_on_refresh_clicked` anfassen."""

    def __init__(self, thread=None):
        self._test_thread = thread
        self.status: list[tuple[str, str]] = []
        self.test_gestartet = 0

    def _set_status(self, text, kind="info"):
        self.status.append((text, kind))

    def _on_test_clicked(self):
        self.test_gestartet += 1


def _mit_dialog_methoden(dialog):
    from ui.dialogs.settings_dialog import SettingsDialog

    dialog._test_laeuft = SettingsDialog._test_laeuft.__get__(dialog)
    dialog._on_refresh_clicked = SettingsDialog._on_refresh_clicked.__get__(dialog)
    return dialog


def test_refresh_startet_keinen_zweiten_test(qapp):
    """Der Kern von B-918: waehrend ein Test laeuft, passiert nichts."""
    d = _mit_dialog_methoden(_Dialog(thread=_Thread(laeuft=True)))

    d._on_refresh_clicked()

    assert d.test_gestartet == 0
    assert d.status and "laeuft bereits" in d.status[-1][0]


def test_refresh_startet_den_test_wenn_keiner_laeuft(qapp):
    d = _mit_dialog_methoden(_Dialog(thread=_Thread(laeuft=False)))

    d._on_refresh_clicked()

    assert d.test_gestartet == 1


def test_refresh_startet_den_test_ohne_vorherigen_thread(qapp):
    """Erster Klick ueberhaupt — `_test_thread` ist None."""
    d = _mit_dialog_methoden(_Dialog(thread=None))

    d._on_refresh_clicked()

    assert d.test_gestartet == 1


def test_abgeraeumter_thread_blockiert_nicht(qapp):
    """Qt kann das C++-Objekt geloescht haben; das darf nicht sperren."""
    class _Tot:
        def isRunning(self):
            raise RuntimeError("Internal C++ object already deleted")

    d = _mit_dialog_methoden(_Dialog(thread=_Tot()))

    d._on_refresh_clicked()

    assert d.test_gestartet == 1


# ── B-925 ────────────────────────────────────────────────────────────────────

def test_das_refresh_fenster_faengt_den_sekundentakt():
    """Die Konvertierungen lagen ~1 s auseinander — 200 ms fassten nichts zusammen."""
    from ui.controllers.media_table import MediaTableController

    assert MediaTableController._REFRESH_FENSTER_MS >= 1000


def test_entprellung_benutzt_das_fenster_statt_einer_festen_zahl():
    """Quellcode-Guard: sonst steht die 200 wieder da."""
    from ui.controllers.media_table import MediaTableController

    src = inspect.getsource(MediaTableController._refresh_media_table_debounced)

    assert "_REFRESH_FENSTER_MS" in src
    assert "singleShot(200" not in src


def test_zweiter_aufruf_im_fenster_setzt_keinen_zweiten_timer(monkeypatch):
    """Ein laufendes Fenster nimmt weitere Meldungen mit, statt neu zu starten."""
    from ui.controllers import media_table as mod

    gesetzt: list[int] = []
    monkeypatch.setattr(
        mod.QTimer, "singleShot",
        staticmethod(lambda ms, _cb: gesetzt.append(ms)),
    )

    class _Fenster:
        _refresh_pending = False

    ctrl = mod.MediaTableController.__new__(mod.MediaTableController)
    ctrl.window = _Fenster()

    ctrl._refresh_media_table_debounced()
    ctrl._refresh_media_table_debounced()
    ctrl._refresh_media_table_debounced()

    assert gesetzt == [mod.MediaTableController._REFRESH_FENSTER_MS]
