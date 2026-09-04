"""B-829: eine nie gezeichnete Pacing-Kurve darf die Cut-Rate-Wahl nicht überstimmen.

`PacingCurveWidget` startet mit `[0.5] * 200` — dem Ruhezustand, nicht der
Eingabe eines Nutzers. `edit_workspace` holt bei jedem Klick bedingungslos
`get_all_densities()` und übergibt das als `manual_density_curve`. In
`_compute_effective_step` gilt eine vorhandene Kurve als höchste Priorität:
`_density_to_beat_step(0.5)` ist 2, und `effective = min(base_step, 2)` macht
aus 4, 8 und 16 jeweils 2.

Gemessen vor dem Fix:

    base | ohne Kurve | mit Default-Kurve
       1 |      1     |       1
       2 |      3     |       3
       4 |      6     |       3
       8 |     12     |       3
      16 |     16     |       3

Vier von fünf Optionen im UI liefern also dasselbe Ergebnis. Der Parameter
heißt `manual_density_curve` — eine Kurve, die nie gezeichnet wurde, ist
nicht manuell. Genau diese Verwechslung prüfen diese Tests.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from services.pacing_edit_helpers import _compute_effective_step


def _step(base: int, kurve):
    return _compute_effective_step(
        base_step=base,
        beat_index=10,
        beat_time=30.0,
        total_duration=120.0,
        energy_per_beat=[0.5] * 100,
        energy_reactivity=50,
        breakdown_behavior="none",
        pacing_curve=kurve,
    )


def test_b829_unberuehrtes_widget_liefert_keinen_override(qtbot):
    """Der Kern: ohne Zeichnung gibt es keine manuelle Kurve."""
    from ui.widgets.pacing_ramp import PacingRampWidget

    widget = PacingRampWidget()
    qtbot.addWidget(widget)

    assert widget.get_manual_override() is None, (
        "B-829: das unberuehrte Widget meldet eine 'manuelle' Kurve. Damit "
        "ueberstimmt der Ruhezustand [0.5]*200 die Cut-Rate-Wahl des Nutzers."
    )


def test_b829_gezeichnete_kurve_wird_als_override_geliefert(qtbot):
    """Gegenprobe: wer zeichnet, soll die Kurve auch bekommen."""
    from ui.widgets.pacing_ramp import PacingRampWidget

    widget = PacingRampWidget()
    qtbot.addWidget(widget)
    widget.set_ramp(0.9, 0.9)  # hohe Dichte, frueher: Strich weit oben

    override = widget.get_manual_override()
    assert override is not None, "gezeichnete Kurve muss als Override gelten"
    assert len(override) == 200
    assert max(override) > 0.5, "die Zeichnung muss sich im Ergebnis zeigen"


def test_b829_reset_macht_die_kurve_wieder_unberuehrt(qtbot):
    from ui.widgets.pacing_ramp import PacingRampWidget

    widget = PacingRampWidget()
    qtbot.addWidget(widget)
    widget.set_ramp(0.9, 0.9)
    assert widget.get_manual_override() is not None

    widget.reset_curve()

    assert widget.get_manual_override() is None, (
        "B-829: nach dem Zuruecksetzen darf die Kurve nicht weiter als "
        "manuelle Vorgabe gelten"
    )


def test_b829_cut_rate_bleibt_ohne_override_unterscheidbar():
    """Ohne Kurve muss jede UI-Stufe ein eigenes Ergebnis liefern.

    Das ist die eigentliche Nutzerzusage: fuenf Auswahlmoeglichkeiten,
    fuenf verschiedene Schnittdichten.
    """
    stufen = [1, 2, 4, 8, 16]
    ergebnisse = [_step(b, None) for b in stufen]

    assert len(set(ergebnisse)) == len(stufen), (
        f"B-829: die Cut-Rate-Stufen {stufen} ergeben nur "
        f"{len(set(ergebnisse))} verschiedene Werte: {ergebnisse}"
    )
    assert ergebnisse == sorted(ergebnisse), (
        f"groessere Beat-Abstaende muessen groessere Schritte ergeben: {ergebnisse}"
    )


def test_b829_default_kurve_kollabiert_die_stufen_dokumentiert():
    """Hält den Mechanismus fest, gegen den der Fix schuetzt.

    Wird eine flache 0.5-Kurve als echter Override uebergeben, ist der Kollaps
    korrektes Verhalten — die Kurve hat laut Design Vorrang. Der Fehler war,
    dass der Ruhezustand als Override durchging.
    """
    flach = [0.5] * 200
    ergebnisse = [_step(b, flach) for b in (2, 4, 8, 16)]

    assert len(set(ergebnisse)) == 1, (
        f"eine flache 0.5-Kurve soll bewusst alles angleichen, ergab: {ergebnisse}"
    )
