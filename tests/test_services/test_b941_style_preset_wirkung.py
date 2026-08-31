"""B-941 — sechs Spalten der Stil-Presets hatten keinen Leser.

`min_clip_duration`, `max_clip_duration`, `beat_weight`, `kick_weight`,
`snare_weight` und `hihat_weight` wurden nirgends gelesen. Angewandt wurden nur
`cut_rate`, `energy_reactivity` und `breakdown_behavior` — "Ambient" (4-15 s)
und "Cinematic" (3-12 s) erzeugten deshalb identische Clip-Laengen.

Userentscheidung 2026-08-31: alle sechs anwenden.
"""

import pytest

from services.pacing_beat_grid import AdvancedPacingSettings
from services.pacing_service import (
    _enforce_min_cut_distance,
    _gewichteter_onset_snap,
)
from services.pacing.style_preset_loader import lade_preset_felder


# ── Untergrenze aus dem Preset ────────────────────────────────────────────

def test_ohne_preset_bleibt_die_alte_untergrenze():
    """B-613: 0.2 s, damit keine Timeline-Luecken entstehen."""
    cuts = [0.0, 0.1, 0.5, 0.55, 3.0]

    assert _enforce_min_cut_distance(cuts, None) == [0.0, 0.5, 3.0]


def test_preset_hebt_die_untergrenze_an():
    cuts = [0.0, 1.0, 2.0, 3.0, 4.0, 12.0]

    eng = _enforce_min_cut_distance(cuts, 4.0)

    assert eng == [0.0, 4.0, 12.0]
    laengen = [b - a for a, b in zip(eng, eng[1:])]
    assert min(laengen) >= 4.0


def test_preset_darf_die_untergrenze_nicht_senken():
    """Unter 0.2 s kaemen die geskippten Mini-Segmente zurueck (B-613)."""
    cuts = [0.0, 0.1, 0.5, 3.0]

    assert _enforce_min_cut_distance(cuts, 0.01) == _enforce_min_cut_distance(cuts, None)


def test_unbrauchbarer_wert_faellt_auf_die_alte_grenze_zurueck():
    cuts = [0.0, 0.1, 0.5, 3.0]

    assert _enforce_min_cut_distance(cuts, "viel") == _enforce_min_cut_distance(cuts, None)


def test_rahmen_bleibt_exakt():
    """Die SCHNITT-Garantie 'Ende == Audio-Dauer' darf nicht kippen."""
    cuts = [0.0, 5.0, 9.9, 10.0]

    eng = _enforce_min_cut_distance(cuts, 4.0)

    assert eng[0] == 0.0
    assert eng[-1] == 10.0


# ── Gewichteter Onset-Snap ────────────────────────────────────────────────

def test_bei_gleichem_gewicht_gewinnt_der_naehere_onset():
    """Und bei Gleichstand mit dem Beat gewinnt der Onset — Verhalten vor B-941."""
    assert _gewichteter_onset_snap(10.0, {1.0: [9.98, 10.04]}, 1.0, 0.05) == 9.98


def test_hoeheres_gewicht_schlaegt_geringeren_abstand():
    """Kick 1.2 bei 30 ms gewinnt gegen Snare 0.5 bei 10 ms."""
    ergebnis = _gewichteter_onset_snap(
        10.0, {1.2: [10.03], 0.5: [10.01]}, beat_weight=0.1, max_shift=0.05)

    assert ergebnis == 10.03


def test_hohes_beat_gewicht_laesst_den_cut_stehen():
    """Wer das Raster hoeher gewichtet als die Drums, bleibt auf dem Beat."""
    ergebnis = _gewichteter_onset_snap(
        10.0, {1.0: [10.02]}, beat_weight=5.0, max_shift=0.05)

    assert ergebnis == 10.0


def test_onsets_ausserhalb_des_fensters_werden_ignoriert():
    ergebnis = _gewichteter_onset_snap(
        10.0, {9.9: [10.4]}, beat_weight=1.0, max_shift=0.05)

    assert ergebnis == 10.0


def test_gewicht_null_schaltet_einen_typ_ab():
    """Hihat 0.0 heisst: Hihat-Onsets zaehlen nicht — wie vor B-941."""
    ergebnis = _gewichteter_onset_snap(
        10.0, {0.0: [10.01], 1.0: [10.04]}, beat_weight=0.1, max_shift=0.05)

    assert ergebnis == 10.04


# ── Preset-Lader ──────────────────────────────────────────────────────────

def test_lader_holt_genau_die_sechs_spalten(test_engine):
    from sqlalchemy.orm import Session
    from database import StylePreset

    with Session(test_engine) as session:
        session.add(StylePreset(
            name="Ambient", cut_rate=0.3, energy_reactivity=0.2,
            breakdown_behavior="none", min_clip_duration=4.0,
            max_clip_duration=15.0, beat_weight=0.5, kick_weight=0.4,
            snare_weight=0.3, hihat_weight=0.1,
        ))
        session.commit()

    felder = lade_preset_felder("Ambient")

    assert felder == {
        "min_clip_duration": 4.0, "max_clip_duration": 15.0,
        "beat_weight": 0.5, "kick_weight": 0.4,
        "snare_weight": 0.3, "hihat_weight": 0.1,
    }
    # Die drei Widget-Spalten gehen weiter ueber die Oberflaeche.
    assert "cut_rate" not in felder
    assert "breakdown_behavior" not in felder
    AdvancedPacingSettings(**felder)  # Feldnamen passen zum Settings-Objekt


@pytest.mark.parametrize("name", ["", None, "   ", "Gibt-Es-Nicht"])
def test_lader_liefert_leer_statt_zu_werfen(name, test_engine):
    assert lade_preset_felder(name) == {}


def test_ohne_preset_bleiben_die_felder_none():
    """Der bisherige Pfad muss unveraendert bleiben, wenn kein Preset greift."""
    s = AdvancedPacingSettings()

    assert s.min_clip_duration is None
    assert s.max_clip_duration is None
    assert s.beat_weight is None
    assert s.kick_weight is None
    assert s.snare_weight is None
    assert s.hihat_weight is None


def test_ambient_und_cinematic_unterscheiden_sich_jetzt(test_engine):
    """Der Kern des Berichts: identische Clip-Laengen trotz anderer Presets."""
    from sqlalchemy.orm import Session
    from database import StylePreset

    with Session(test_engine) as session:
        session.add_all([
            StylePreset(name="Ambient", min_clip_duration=4.0, max_clip_duration=15.0),
            StylePreset(name="Cinematic", min_clip_duration=3.0, max_clip_duration=12.0),
        ])
        session.commit()

    cuts = [0.0, 3.2, 6.5, 9.9, 20.0]
    ambient = _enforce_min_cut_distance(
        cuts, lade_preset_felder("Ambient")["min_clip_duration"])
    cinematic = _enforce_min_cut_distance(
        cuts, lade_preset_felder("Cinematic")["min_clip_duration"])

    assert ambient != cinematic


# ── B-942: Nachwirkung der Untergrenze auf die Obergrenze ─────────────────

def test_b942_ausduennen_darf_die_obergrenze_nicht_sprengen():
    """Regression aus dem ersten Live-Lauf von B-941.

    `_enforce_min_cut_distance` entfernt Cuts — die Segmente dazwischen
    wachsen dabei ueber die Obergrenze. Im Ambient-Lauf am 2026-08-31 blieben
    so zwei Segmente mit 10.91 s und 10.50 s stehen, obwohl kein Clip laenger
    als 10.00 s ist. Ihre Quelle wurde gekappt, und die Timeline-Reparatur
    schloss 38 Luecken und erzeugte 6 Ueberlappungen.
    """
    from services.pacing_edit_helpers import _enforce_max_segment_duration

    # Vier dicht liegende Cuts am Anfang: die Mindestlaenge 4 s wirft drei
    # davon weg und laesst ein 9-Sekunden-Segment zurueck.
    cuts = [0.0, 1.0, 2.0, 3.0, 9.0, 16.0]
    beats = [float(i) * 0.5 for i in range(40)]

    ausgeduennt = _enforce_min_cut_distance(cuts, 4.0)
    laengen_vorher = [b - a for a, b in zip(ausgeduennt, ausgeduennt[1:])]
    assert max(laengen_vorher) > 7.0, "Aufbau trifft den Fall nicht mehr"

    danach = _enforce_max_segment_duration(ausgeduennt, beats, 7.0)
    laengen = [b - a for a, b in zip(danach, danach[1:])]

    assert max(laengen) <= 7.05


def test_b942_teilen_unterlaeuft_die_mindestlaenge_nicht():
    """Beim Teilen darf kein Schnipsel unter der Mindestlaenge entstehen."""
    from services.pacing_edit_helpers import _enforce_max_segment_duration

    beats = [float(i) * 0.5 for i in range(40)]
    geteilt = _enforce_max_segment_duration([0.0, 8.5], beats, 7.79)
    laengen = [b - a for a, b in zip(geteilt, geteilt[1:])]

    assert min(laengen) >= 1.0, f"zu kurzer Rest: {laengen}"
