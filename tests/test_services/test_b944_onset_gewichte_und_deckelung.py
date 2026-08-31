"""B-944 — zwei Defekte aus der Selbstpruefung der B-941/B-942-Arbeit.

1. ``_gewichteter_onset_snap`` bekam seine Kandidaten als ``{gewicht: zeiten}``.
   Trugen zwei Trommeln dasselbe Gewicht — ``kick_weight == snare_weight`` ist
   die naheliegendste Einstellung ueberhaupt — ueberschrieb der zweite Eintrag
   den ersten und ein kompletter Onset-Typ verschwand lautlos.

2. B-942 senkte die Segment-Obergrenze global auf den KUERZESTEN Clip im Pool.
   Ein einziger 1.5-Sekunden-Schnipsel haette damit jedes Segment des ganzen
   Videos auf 1.5 s gedeckelt. Ersetzt durch eine Auswahl pro Segment.
"""

import inspect

import pytest

from services.pacing_service import (
    _auto_edit_phase3_inner,
    _clips_die_das_segment_tragen,
    _gewichteter_onset_snap,
)


# ── 1. Gewichts-Kollision ─────────────────────────────────────────────────

def test_gleiche_gewichte_loeschen_keinen_onset_typ_mehr():
    """Kick und Snare beide 1.0: der naehere Onset (Kick) muss gewinnen."""
    kandidaten = [(1.0, [10.02]), (1.0, [10.04]), (0.3, [])]

    assert _gewichteter_onset_snap(10.0, kandidaten, 1.0, 0.05) == 10.02


def test_reihenfolge_der_kandidaten_aendert_das_ergebnis_nicht():
    vorwaerts = _gewichteter_onset_snap(
        10.0, [(1.0, [10.02]), (1.0, [10.04])], 1.0, 0.05)
    rueckwaerts = _gewichteter_onset_snap(
        10.0, [(1.0, [10.04]), (1.0, [10.02])], 1.0, 0.05)

    assert vorwaerts == rueckwaerts == 10.02


def test_hoeheres_gewicht_gewinnt_weiterhin_gegen_naehe():
    ergebnis = _gewichteter_onset_snap(
        10.0, [(1.2, [10.03]), (0.5, [10.01])], beat_weight=0.1, max_shift=0.05)

    assert ergebnis == 10.03


# ── 2. Clip-Auswahl statt globaler Deckelung ──────────────────────────────

@pytest.fixture
def pool():
    return {1: {"duration": 10.0}, 2: {"duration": 9.5}, 3: {"duration": 1.5}}


def test_zu_kurze_clips_fallen_raus(pool):
    """Der 1.5-s-Schnipsel darf ein 8-s-Segment nicht zugewiesen bekommen."""
    assert _clips_die_das_segment_tragen([1, 2, 3], pool, 8.0) == [1, 2]


def test_ein_kurzer_clip_deckelt_nicht_mehr_den_ganzen_pool(pool):
    """Kern der Regression: vorher senkte er die Obergrenze global auf 1.5 s."""
    tragende = _clips_die_das_segment_tragen([1, 2, 3], pool, 9.4)

    assert tragende == [1, 2]
    assert 3 not in tragende


def test_ohne_tragenden_clip_bleibt_die_volle_liste(pool):
    """Eine gekappte Quelle ist immer noch besser als gar kein Clip."""
    assert _clips_die_das_segment_tragen([1, 2, 3], pool, 60.0) == [1, 2, 3]


def test_toleranz_von_50ms(pool):
    """Ein Clip, der das Segment um <50 ms verfehlt, zaehlt noch als tragend."""
    assert 2 in _clips_die_das_segment_tragen([1, 2], pool, 9.53)


def test_fehlende_dauer_zaehlt_als_zu_kurz():
    unvollstaendig = {1: {"duration": 10.0}, 2: {}}

    assert _clips_die_das_segment_tragen([1, 2], unvollstaendig, 5.0) == [1]


def test_globale_deckelung_auf_den_kuerzesten_clip_ist_weg():
    """Quellcode-Guard gegen einen Rueckfall in die zu grobe Loesung."""
    src = inspect.getsource(_auto_edit_phase3_inner)

    assert "_kuerzester" not in src, (
        "Die Obergrenze darf nicht wieder global auf den kuerzesten Clip "
        "gesenkt werden — ein einzelner kurzer Clip deckelte damit alles."
    )


def test_studio_brain_wahl_wird_auf_laenge_geprueft():
    """Quellcode-Guard: die Brain-Pipeline ging am Laengenfilter vorbei.

    Sie waehlt ihren Clip selbst; ohne diese Pruefung landete ein 8.00-s-Clip
    in einem 9.58-s-Segment (gemessen 2026-08-31, Flag ist in dieser
    Installation aktiv).
    """
    src = inspect.getsource(_auto_edit_phase3_inner)
    block = src.split("_sb_chosen_vid is not None", 1)[1][:800]

    assert "_sb_dur" in block
    assert "seg_duration" in block
