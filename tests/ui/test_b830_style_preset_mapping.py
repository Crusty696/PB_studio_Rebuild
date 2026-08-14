"""B-830: Style-Presets werden invertiert und kollabiert auf die Cut-Rate abgebildet.

`StylePreset.cut_rate` ist ein **Faktor** (0.3 bis 1.8 in den Defaults, siehe
`database/migrations.py`): hoeher heisst schnellere Cuts. Die Combo-Box fuehrt
dagegen **Beat-Abstaende** (1, 2, 4, 8, 16): hoeher heisst langsamere Cuts.

`_apply_style_preset` behandelte beides als dieselbe Groesse und suchte den
numerisch naechsten Beat-Wert:

```python
closest_beat = min(cut_rate_map.keys(), key=lambda x: abs(x - preset.cut_rate))
```

Ergebnis: alle Presets ausser Festival landen auf "1 Beat", Festival auf
"2 Beat". Ambient (0.3, "atmosphaerisch, lange Clips") bekommt damit
SCHNELLERE Cuts als Festival (1.8, "Maximum Energy, schnellste Cuts") — die
Reihenfolge ist umgekehrt und der gesamte Bereich auf zwei Stufen gestaucht.

Diese Tests pruefen die Zuordnung gegen die Beschreibung jedes Presets.
"""

from __future__ import annotations

import pytest

from ui.controllers.edit_workspace import cut_rate_faktor_zu_beat_index

# Beat-Abstand je Combo-Index, wie in tab_pacing_anker.py aufgebaut.
_INDEX_ZU_BEATS = {0: 1, 1: 2, 2: 4, 3: 8, 4: 16}

# (Name, cut_rate, Beschreibung aus database/migrations.py)
_DEFAULT_PRESETS = [
    ("Ambient", 0.3, "Atmosphaerisch, lange Clips"),
    ("Cinematic", 0.5, "Filmisch, dramatische Uebergaenge"),
    ("Hip-Hop", 0.6, "Laid-back, langsame Cuts"),
    ("Minimal", 0.7, "Reduziert, subtile Wechsel"),
    ("House", 0.8, "Groovy, mittleres Tempo"),
    ("Standard", 1.0, "Ausgewogener Mix"),
    ("Techno", 1.2, "Kick-betont, schnelle Cuts"),
    ("Drum & Bass", 1.5, "Schnell, Snare-fokussiert"),
    ("Festival", 1.8, "Maximum Energy, schnellste Cuts"),
]


def _beats(cut_rate: float) -> int:
    return _INDEX_ZU_BEATS[cut_rate_faktor_zu_beat_index(cut_rate)]


def test_b830_hoehere_cut_rate_ergibt_nie_langsamere_cuts():
    """Der Kern: die Reihenfolge darf nicht umgekehrt sein."""
    sortiert = sorted(_DEFAULT_PRESETS, key=lambda p: p[1])
    beats = [_beats(rate) for _, rate, _ in sortiert]

    assert beats == sorted(beats, reverse=True), (
        "B-830: hoehere cut_rate muss kuerzere Beat-Abstaende ergeben. "
        + ", ".join(
            f"{name}({rate})->{b} Beat"
            for (name, rate, _), b in zip(sortiert, beats)
        )
    )


def test_b830_ambient_ist_langsamer_als_festival():
    """Das sprechendste Gegenbeispiel aus dem Bugreport."""
    ambient = _beats(0.3)
    festival = _beats(1.8)

    assert ambient > festival, (
        f"B-830: Ambient ('lange Clips') ergibt {ambient} Beat, Festival "
        f"('schnellste Cuts') {festival} Beat — das ist verkehrt herum."
    )


def test_b830_der_ganze_regelbereich_wird_genutzt():
    """Neun Presets duerfen nicht auf zwei Stufen zusammenfallen."""
    beats = {_beats(rate) for _, rate, _ in _DEFAULT_PRESETS}

    assert len(beats) >= 4, (
        f"B-830: die neun Default-Presets belegen nur {len(beats)} von fuenf "
        f"Stufen: {sorted(beats)}"
    )


def test_b830_die_extreme_treffen_die_raender():
    assert _beats(1.8) == 1, "das schnellste Preset gehoert auf 1 Beat"
    assert _beats(0.3) == 16, "das langsamste Preset gehoert auf 16 Beat"


@pytest.mark.parametrize("name,rate,beschreibung", _DEFAULT_PRESETS)
def test_b830_jedes_preset_liefert_einen_gueltigen_index(name, rate, beschreibung):
    idx = cut_rate_faktor_zu_beat_index(rate)
    assert idx in _INDEX_ZU_BEATS, f"{name}: Index {idx} liegt ausserhalb der Combo"


def test_b830_werte_ausserhalb_des_bereichs_landen_in_der_mitte():
    """Ein kaputtes Preset darf nicht still zum Extrem werden.

    Verglichen wird der Beat-Abstand, nicht der Combo-Index — sonst
    verwechselt man die beiden gegenlaeufigen Groessen genau wie der Bug.
    """
    assert _beats(0.0) == 4, "0 ist kein gueltiger Faktor -> neutrale Mitte"
    assert _beats(-5.0) == 4, "negativ ist kein gueltiger Faktor -> Mitte"
    assert _beats(None) == 4, "fehlender Wert -> Mitte"

    # Ein sehr hoher Faktor ist plausibel gemeint: so schnell wie moeglich.
    assert _beats(99.0) == 1
