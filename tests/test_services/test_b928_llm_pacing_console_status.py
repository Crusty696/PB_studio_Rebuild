"""B-928: Die Konsolenmeldung zum LLM-Pacing muss der Wahrheit entsprechen.

Vorher schrieb die Oberflaeche bei jedem Lauf "LLM-Pacing aktiv:
Strategist=True", waehrend `services/pacing_service.py` den Strategisten
uebersprang, sobald `musikgetriebener_schnitt` gilt — und dieses Feld hat
Default True und wird repo-weit nie auf False gesetzt.

Der Vertrag hier: die Meldung nennt "uebersprungen" genau dann, wenn der
Produktivpfad tatsaechlich ueberspringt, und bleibt sonst unveraendert.
"""
from __future__ import annotations

import pytest

from services.pacing_beat_grid import AdvancedPacingSettings
from ui.controllers.edit_workspace import _llm_pacing_console_status


def _settings(**kw) -> AdvancedPacingSettings:
    return AdvancedPacingSettings(**kw)


def test_strategist_wird_als_uebersprungen_gemeldet():
    """Der Kernfall: Checkbox an, musikgetriebener Schnitt aktiv."""
    text = _llm_pacing_console_status(
        _settings(use_llm_strategist=True, use_llm_pacing=False)
    )
    assert text is not None
    assert "uebersprungen (musikgetriebener Schnitt)" in text
    assert "Strategist=True" not in text, (
        "die alte Falschaussage darf nicht mehr auftauchen"
    )


def test_meldung_folgt_derselben_bedingung_wie_der_produktivpfad():
    """Gegenprobe: ohne musikgetriebenen Schnitt laeuft der Strategist wirklich."""
    settings = _settings(use_llm_strategist=True, use_llm_pacing=False)
    settings.musikgetriebener_schnitt = False

    # Dieselbe Bedingung wie services/pacing_service.py:857-860
    strategist_ohne_wirkung = (
        settings.use_llm_strategist
        and getattr(settings, "musikgetriebener_schnitt", False)
    )
    assert strategist_ohne_wirkung is False

    text = _llm_pacing_console_status(settings)
    assert "Strategist=True" in text
    assert "uebersprungen" not in text


def test_edl_pacing_bleibt_unveraendert_sichtbar():
    """EDL-Pacing ist von der Strategist-Frage unberuehrt."""
    text = _llm_pacing_console_status(
        _settings(use_llm_strategist=False, use_llm_pacing=True)
    )
    assert "Strategist=False" in text
    assert "EDL-Pacing=True" in text


def test_ohne_llm_keine_meldung():
    """Sind beide Schalter aus, schweigt die Konsole wie bisher."""
    assert _llm_pacing_console_status(
        _settings(use_llm_strategist=False, use_llm_pacing=False)
    ) is None


@pytest.mark.parametrize("strategist,edl", [(True, True), (True, False), (False, True)])
def test_meldung_nennt_immer_beide_schalter(strategist: bool, edl: bool):
    """Format bleibt stabil: beide Angaben plus Backend-Hinweis."""
    text = _llm_pacing_console_status(
        _settings(use_llm_strategist=strategist, use_llm_pacing=edl)
    )
    assert text.startswith("[Auto-Edit] LLM-Pacing:")
    assert "Strategist=" in text
    assert f"EDL-Pacing={edl}" in text
    assert text.endswith("(Ollama).")
