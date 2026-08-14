"""B-833: UI-Texte im SCHNITT versprechen etwas anderes, als der Code tut.

Drei Stellen wichen vom tatsächlichen Verhalten ab:

1. Tooltip von „Timeline generieren": „Timeline aus Audio, Videoauswahl und
   Pacing-Einstellungen neu generieren." Der Button zeichnet aber nur
   Beat-Marker und Cut-Linien; `calculate_cut_points` schreibt nichts in die
   Datenbank, es entstehen keine Clips.
2. Tooltip von „Mit neuen Pacing-Einstellungen generieren": „Clips/Cuts
   koennen ersetzt oder verschoben werden" plus die Zusage, Stil- und
   Ankerwerte zu berücksichtigen. Der Button landet im selben Codepfad wie (1)
   und liest weder Anker noch Style.
3. Die Empty-State-Kachel „Festival" verspricht „1 Beat", das zugehörige
   Profil setzt aber Combo-Index 1 — also 2 Beat. Die DB-Presets
   (`cut_rate 1.8`) meinen ebenfalls die schnellste Stufe.

Diese Tests halten fest, dass Beschriftung und Verhalten zusammenpassen.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

# Combo-Reihenfolge aus tab_pacing_anker.py
_INDEX_ZU_BEATS = {0: 1, 1: 2, 2: 4, 3: 8, 4: 16}


def test_b833_festival_profil_entspricht_seiner_beschriftung():
    """Die Kachel verspricht 1 Beat — das Profil muss das auch setzen."""
    import re
    from services.pacing_profile import _PRESETS
    from ui.workspaces.schnitt.empty_view import _PRESETS as KACHELN

    beschreibungen = dict(KACHELN)
    for name, profil in _PRESETS.items():
        text = beschreibungen.get(name)
        if not text:
            continue
        treffer = re.search(r"(\d+)\s*Beat", text)
        assert treffer, f"{name}: Beschreibung nennt keine Beat-Zahl: {text!r}"
        versprochen = int(treffer.group(1))
        tatsaechlich = _INDEX_ZU_BEATS[profil["cut_rate_index"]]
        assert versprochen == tatsaechlich, (
            f"B-833: Kachel '{name}' verspricht {versprochen} Beat, das Profil "
            f"setzt aber {tatsaechlich} Beat (Index {profil['cut_rate_index']})."
        )


def test_b833_reaktivitaet_der_kacheln_stimmt():
    """Gleiche Zusage für den zweiten Wert auf der Kachel."""
    import re
    from services.pacing_profile import _PRESETS
    from ui.workspaces.schnitt.empty_view import _PRESETS as KACHELN

    beschreibungen = dict(KACHELN)
    for name, profil in _PRESETS.items():
        text = beschreibungen.get(name)
        if not text:
            continue
        treffer = re.search(r"Reaktivität\s*(\d+)\s*%", text)
        if not treffer:
            continue
        assert int(treffer.group(1)) == profil["energy_reactivity"], (
            f"B-833: Kachel '{name}' verspricht Reaktivität "
            f"{treffer.group(1)} %, das Profil setzt {profil['energy_reactivity']} %."
        )


def test_b833_tooltip_generieren_verspricht_keine_clips(qtbot):
    """Der Button erzeugt keine Clips — der Tooltip darf das nicht behaupten."""
    from ui.workspaces.schnitt.editor_view import SchnittEditorView

    view = SchnittEditorView()
    qtbot.addWidget(view)
    tip = view.btn_generate.toolTip().lower()

    assert "keine clips" in tip, (
        f"B-833: der Tooltip sagt nicht, dass keine Clips entstehen: {tip!r}"
    )
    assert "auto-edit" in tip, (
        "der Tooltip sollte auf den Weg verweisen, der wirklich schneidet"
    )


def test_b833_tooltip_regenerate_verspricht_keine_clipaenderung(qtbot):
    from ui.workspaces.schnitt.tab_pacing_anker import SchnittTabPacingAnker

    tab = SchnittTabPacingAnker()
    qtbot.addWidget(tab)
    tip = tab.btn_regenerate.toolTip().lower()

    assert "keine clips" in tip, (
        f"B-833: der Tooltip behauptet weiterhin Clip-Aenderungen: {tip!r}"
    )
    assert "ersetzt oder verschoben" not in tip.replace("keine clips erzeugt, ersetzt oder verschoben", ""), (
        "die alte Zusage 'Clips koennen ersetzt oder verschoben werden' darf "
        "nicht mehr als Wirkung dastehen"
    )
