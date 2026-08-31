"""B-952 — musikgetriebener Schnitt war nicht abschaltbar.

``AdvancedPacingSettings.musikgetriebener_schnitt`` stand auf ``True`` und
wurde repo-weit nirgends auf ``False`` gesetzt. Folge: der LLM-Strategist wurde
bei **jedem** Lauf uebersprungen, weil seine Section-Map in diesem Modus nicht
gelesen wird (``pacing_service.py:857-866``) — die Checkbox daneben versprach
also etwas, das nie eintrat (B-928).

Userentscheidung 2026-08-31: den musikgetriebenen Schnitt schaltbar machen,
statt die Strategist-Checkbox auszugrauen.
"""

from __future__ import annotations

import pytest

from services.pacing_beat_grid import AdvancedPacingSettings
from ui.controllers.edit_workspace import _llm_pacing_console_status
from ui.workspaces.schnitt.tab_pacing_anker import SchnittTabPacingAnker


@pytest.fixture
def tab(qapp):
    t = SchnittTabPacingAnker()
    yield t
    t.deleteLater()


def test_schalter_existiert_und_ist_bedienbar(tab):
    assert tab.chk_musikgetrieben is not None
    assert tab.chk_musikgetrieben.isEnabled()
    assert "Musikgetrieben" in tab.chk_musikgetrieben.text()


def test_schalter_steht_standardmaessig_an(tab):
    """Das bisherige Verhalten bleibt, solange niemand den Haken entfernt."""
    assert tab.chk_musikgetrieben.isChecked()


def test_tooltip_nennt_die_folge_fuer_den_strategisten(tab):
    """Der Zusammenhang ist nicht offensichtlich und gehoert an den Schalter."""
    tip = tab.chk_musikgetrieben.toolTip()

    assert "LLM-Strategist" in tip
    assert "uebersprungen" in tip or "wirksam" in tip


def test_umschalten_wird_persistiert(qapp, monkeypatch):
    """Der Tab muss NACH dem Patch gebaut werden.

    Die ``toggled``-Lambda bindet ``get_settings_store`` beim Aufbau; ein
    spaeterer Patch erreicht sie nicht mehr. Genau daran ist die erste Fassung
    dieses Tests gescheitert.
    """
    gespeichert = {}

    class _Store:
        def set_nested(self, *pfad, value):
            gespeichert[pfad] = value

        def get_nested(self, *pfad, default=None):
            return gespeichert.get(pfad, default)

    import services.settings_store as store_modul

    monkeypatch.setattr(store_modul, "get_settings_store", lambda: _Store())

    eigener_tab = SchnittTabPacingAnker()
    try:
        eigener_tab.chk_musikgetrieben.setChecked(False)

        assert gespeichert.get(("pacing", "musikgetriebener_schnitt")) is False
    finally:
        eigener_tab.deleteLater()


# ── Wirkung auf die Konsolenmeldung aus B-928 ────────────────────────────

def test_meldung_bei_eingeschaltetem_musikgetriebenen_schnitt():
    s = AdvancedPacingSettings(use_llm_strategist=True, musikgetriebener_schnitt=True)

    assert "uebersprungen (musikgetriebener Schnitt)" in _llm_pacing_console_status(s)


def test_meldung_wenn_der_schalter_aus_ist():
    """Jetzt erreichbar: der Strategist laeuft wirklich."""
    s = AdvancedPacingSettings(use_llm_strategist=True, musikgetriebener_schnitt=False)

    meldung = _llm_pacing_console_status(s)

    assert "Strategist=True" in meldung
    assert "uebersprungen" not in meldung


def test_controller_reicht_den_schalter_durch():
    """Quellcode-Guard: ohne diese Zeile bliebe der Schalter wirkungslos."""
    import inspect

    from ui.controllers.edit_workspace import EditWorkspaceController

    src = inspect.getsource(EditWorkspaceController)

    assert "musikgetriebener_schnitt=_musikgetrieben" in src
    assert '"pacing", "musikgetriebener_schnitt", default=True' in src
