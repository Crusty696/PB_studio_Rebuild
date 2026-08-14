"""B-836: Der Reaktivitaets-Regler stand auf beiden Seiten derselben Ungleichung.

``ui/controllers/edit_workspace.py`` baute die Vorschau-Einstellungen so::

    settings = PacingSettings(
        tempo=tempo_val,
        energy=reactivity,
        cut_density=reactivity,   # <- derselbe Wert ein zweites Mal
        ...

In ``services/pacing_service.py`` wird daraus:

* die Staerke jedes Cuts — ``strength = min(1.0, energy/100 + 0.3)``
  (``pacing_service.py:201``), auf jedem vierten Beat plus 0,15
* die Filterschwelle — ``threshold = 1.0 - cut_density/100``
  (``pacing_service.py:253``), gefiltert wird auf ``strength >= threshold``

Weil beide Groessen aus demselben Regler kamen, lautete die Bedingung
``r/100 + 0.45 >= 1 - r/100``, also ``r >= 27,5``. Unterhalb davon fielen ALLE
Cuts weg: die Timeline blieb leer, ohne Meldung, und die Cut-Rate-Wahl war
zusaetzlich wirkungslos. Der Regler hatte damit faktisch zwei Zustaende.

User-Anweisung 2026-08-14: entkoppeln.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from services.pacing_beat_grid import PacingSettings  # noqa: E402


def _schwelle(settings: PacingSettings) -> float:
    """Die Filterschwelle aus pacing_service.py:253."""
    return 1.0 - (settings.cut_density / 100.0)


def _staerke(settings: PacingSettings, vierter_beat: bool = False) -> float:
    """Die Cut-Staerke aus pacing_service.py:201-203."""
    strength = min(1.0, settings.energy / 100.0 + 0.3)
    if vierter_beat:
        strength = min(1.0, strength + 0.15)
    return strength


def _baue_settings(reaktivitaet: int) -> PacingSettings:
    """Genau die Zuordnung, die edit_workspace fuer die Vorschau benutzt."""
    from ui.controllers.edit_workspace import vorschau_cut_density

    return PacingSettings(
        tempo=50,
        energy=reaktivitaet,
        cut_density=vorschau_cut_density(reaktivitaet),
    )


@pytest.mark.parametrize("reaktivitaet", [0, 5, 10, 20, 27, 30, 50, 80, 100])
def test_kein_reglerwert_filtert_alle_cuts_weg(reaktivitaet):
    settings = _baue_settings(reaktivitaet)
    assert _staerke(settings) >= _schwelle(settings), (
        f"B-836: bei Reaktivitaet {reaktivitaet} % liegt die Cut-Staerke "
        f"{_staerke(settings):.2f} unter der Schwelle {_schwelle(settings):.2f} "
        "— die Timeline bliebe leer."
    )


def test_regler_steht_nicht_mehr_auf_beiden_seiten():
    """Der Kern des Fehlers: cut_density darf nicht mehr mitwandern."""
    werte = {r: _baue_settings(r).cut_density for r in (0, 25, 50, 75, 100)}
    assert len(set(werte.values())) == 1, (
        f"B-836: cut_density folgt weiterhin dem Reaktivitaets-Regler: {werte}"
    )


def test_reaktivitaet_wirkt_weiterhin_auf_die_cut_staerke():
    """Entkoppeln heisst nicht abschalten — energy muss der Regler bleiben."""
    schwach = _baue_settings(0)
    stark = _baue_settings(100)
    assert _staerke(stark) > _staerke(schwach), (
        "die Reaktivitaet muss die Cut-Staerke weiterhin beeinflussen"
    )


def test_niedrige_reaktivitaet_erzeugt_nicht_weniger_cuts_als_hohe():
    """Gegenprobe zum alten Verhalten: 20 % lieferte 0 Cuts, 30 % dann 160."""
    niedrig = _baue_settings(20)
    hoch = _baue_settings(30)
    assert (_staerke(niedrig) >= _schwelle(niedrig)) == (
        _staerke(hoch) >= _schwelle(hoch)
    ), "B-836: es gibt weiterhin eine Schwelle, an der die Timeline umkippt"
