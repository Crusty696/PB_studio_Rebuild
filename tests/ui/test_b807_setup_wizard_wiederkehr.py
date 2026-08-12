"""B-807: der First-Run-Wizard kam bei jedem Start wieder.

Live beobachtet 2026-08-12: beim App-Start erschien der SetupWizard mit
"First-Run erkannt", obwohl die App laengst konfiguriert war. Die Log-Historie
belegt es — die Zeile steht dreimal in den vorhandenen Logs.

Ursache: ``mark_setup_complete()`` wurde nur von ``_skip()``, ``_launch()`` und
dem abgeschlossenen Download gerufen. Wer den Dialog mit **Esc** oder dem
**Fenster-X** schloss, setzte das Flag nie — und bekam ihn beim naechsten Start
erneut.

Getestet wird gegen eine eigene QSettings-Organisation, damit die echten
Einstellungen des Nutzers unberuehrt bleiben.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDialog


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def isolierte_settings(monkeypatch):
    """Eigene Registry-Wurzel — die echten Nutzereinstellungen bleiben heil."""
    from ui.dialogs import setup_wizard

    org, app_name = "PBStudioTest", "B807"
    monkeypatch.setattr(setup_wizard, "_SETTINGS_ORG", org)
    monkeypatch.setattr(setup_wizard, "_SETTINGS_APP", app_name)
    s = QSettings(org, app_name)
    s.remove(setup_wizard._SETUP_KEY)
    s.sync()
    yield s
    s.remove(setup_wizard._SETUP_KEY)
    s.sync()


def test_b807_esc_markiert_den_wizard_als_gesehen(isolierte_settings):
    """Esc/reject muss das Flag setzen — sonst kehrt der Dialog wieder."""
    _ensure_qapp()
    from ui.dialogs.setup_wizard import SetupWizard, is_setup_complete

    assert is_setup_complete() is False, "Vorbedingung: Flag ist ungesetzt"

    w = SetupWizard()
    w.reject()  # genau das, was Esc ausloest

    assert is_setup_complete() is True, (
        "B-807: nach dem Wegklicken per Esc ist der Wizard nicht als gesehen "
        "markiert — er erscheint beim naechsten Start erneut."
    )


def test_b807_fenster_schliessen_markiert_ebenfalls(isolierte_settings):
    """Der Fenster-X-Weg laeuft ueber closeEvent, nicht ueber done()."""
    _ensure_qapp()
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QCloseEvent

    from ui.dialogs.setup_wizard import SetupWizard, is_setup_complete

    assert is_setup_complete() is False

    w = SetupWizard()
    w.closeEvent(QCloseEvent())

    assert is_setup_complete() is True, (
        "B-807: Schliessen ueber das Fenster-X markiert den Wizard nicht als "
        "gesehen."
    )


def test_b807_skip_funktioniert_weiterhin(isolierte_settings):
    """Regressionsschutz: der bisherige Weg darf nicht kaputtgehen."""
    _ensure_qapp()
    from ui.dialogs.setup_wizard import SetupWizard, is_setup_complete

    w = SetupWizard()
    w._skip()

    assert is_setup_complete() is True
    assert w.result() == QDialog.DialogCode.Accepted


def test_b807_produktivcode_markiert_beide_ausgaenge():
    """Belegt am echten Code, dass beide Schliesswege das Flag setzen."""
    import inspect

    from ui.dialogs.setup_wizard import SetupWizard

    done_src = inspect.getsource(SetupWizard.done)
    close_src = inspect.getsource(SetupWizard.closeEvent)

    assert "_mark_seen" in done_src, (
        "B-807: done() (Esc/reject) markiert den Wizard nicht als gesehen."
    )
    assert "_mark_seen" in close_src, (
        "B-807: closeEvent() (Fenster-X) markiert den Wizard nicht als gesehen."
    )
