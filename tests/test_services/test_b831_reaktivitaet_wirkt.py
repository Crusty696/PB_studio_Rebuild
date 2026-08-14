"""B-831: Der Reaktivitäts-Regler wirkt gegenteilig bzw. gar nicht.

Zwei getrennte Defekte in `_compute_effective_step`
(`services/pacing_edit_helpers.py`):

**1. Reaktivität 0 kehrt die Wirkung um.**

```python
if reactivity > 0 and beat_index < len(energy_per_beat):
    energy = energy_per_beat[beat_index]
else:
    energy = 0.5      # <- greift auch bei reactivity == 0
```

Bei 0 % wird die Energie also nicht ignoriert, sondern auf 0.5 gesetzt. Damit
greift der Zweig ``elif 0.3 <= energy <= 0.5: energy_step = effective * 1.5``
und der Schnitt wird **langsamer**. Beschriftet ist der Regler als
"Reaktivität" — 0 muss heissen: die Energie beeinflusst nichts.

**2. Zwischen 50 % und 100 % ist kein Unterschied messbar.**

Die mittlere Modulation ist mit festem Faktor 1.5 verdrahtet und ignoriert
`reactivity` komplett. Nur der Zweig für hohe Energie (>0.7) nutzt den Regler.
Für alles dazwischen ist er wirkungslos.
"""

from __future__ import annotations

import pytest

from services.pacing_edit_helpers import _compute_effective_step


def _step(reactivity: int, energy: float, base: int = 4) -> int:
    return _compute_effective_step(
        base_step=base,
        beat_index=10,
        beat_time=30.0,
        total_duration=120.0,
        energy_per_beat=[energy] * 100,
        energy_reactivity=reactivity,
        breakdown_behavior="none",
        pacing_curve=None,
    )


def test_b831_reaktivitaet_null_laesst_den_schritt_unveraendert():
    """0 % heisst: die Energie aendert nichts — weder schneller noch langsamer."""
    base = 4
    for energy in (0.1, 0.4, 0.5, 0.9):
        ergebnis = _step(0, energy, base=base)
        assert ergebnis == base, (
            f"B-831: bei Reaktivitaet 0 und Energie {energy} kam {ergebnis} "
            f"statt {base} heraus. Der Regler wirkt, obwohl er auf null steht."
        )


def test_b831_reaktivitaet_null_macht_nicht_langsamer():
    """Der konkrete Fehler aus dem Bugreport, als eigener Vertrag."""
    ohne = _step(0, 0.4)
    voll = _step(100, 0.4)

    assert ohne <= voll, (
        f"B-831: Reaktivitaet 0 ergibt {ohne}, Reaktivitaet 100 ergibt {voll} — "
        "null darf nicht langsamer schneiden als voll."
    )


def test_b831_mittlere_reaktivitaet_liegt_zwischen_den_extremen():
    """50 % muss sich von 100 % unterscheiden, sonst ist der Regler Zierde."""
    werte = {r: _step(r, 0.4) for r in (0, 50, 100)}

    assert len(set(werte.values())) > 1, (
        f"B-831: alle Reaktivitaetsstufen liefern dasselbe Ergebnis: {werte}"
    )
    assert werte[0] <= werte[50] <= werte[100] or werte[0] >= werte[50] >= werte[100], (
        f"B-831: die Wirkung ist nicht monoton: {werte}"
    )


def test_b831_hohe_energie_reagiert_weiterhin_auf_den_regler():
    """Gegenprobe: der bestehende, funktionierende Zweig bleibt erhalten."""
    schwach = _step(20, 0.9, base=8)
    stark = _step(100, 0.9, base=8)

    assert stark < schwach, (
        f"bei hoher Energie muss mehr Reaktivitaet zu kuerzeren Abstaenden "
        f"fuehren — 20%%: {schwach}, 100%%: {stark}"
    )


def test_b831_breakdown_bleibt_unabhaengig_von_der_reaktivitaet():
    """`breakdown_behavior` haengt nicht am Reaktivitaets-Regler.

    Das ist bewusst so: leise Passagen folgen einer eigenen Einstellung.
    """
    halbiert = _compute_effective_step(
        base_step=4, beat_index=10, beat_time=30.0, total_duration=120.0,
        energy_per_beat=[0.1] * 100, energy_reactivity=100,
        breakdown_behavior="halve", pacing_curve=None,
    )
    assert halbiert > 4, "halve muss bei leiser Passage laengere Abstaende geben"
