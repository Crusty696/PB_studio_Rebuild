"""Die Auswahllogik gegen Material, das Randfaelle enthaelt.

Das Testprojekt hat 121 Clips zwischen 7.79 und 10.00 s. Genau deshalb blieb
die zu grobe Deckelung aus B-942 dort unsichtbar. Diese Tests laufen gegen
Pools mit Schnipseln, gemischten Laengen und fehlender Dauer.
"""

import pytest

from services.pacing_service import _clips_die_das_segment_tragen
from tests.fixtures.clip_pools import (
    ALLE_POOLS,
    POOL_ALLE_ZU_KURZ,
    POOL_GEMISCHT,
    POOL_MIT_SCHNIPSEL,
    POOL_OHNE_DAUER,
    clip_ids,
    kuerzester,
    video_info,
)


def test_ein_schnipsel_beschraenkt_nur_sich_selbst():
    """Der Kern von B-944: der 1.5-s-Clip darf die anderen nicht mitziehen."""
    pool = POOL_MIT_SCHNIPSEL
    info = video_info(pool)

    tragende = _clips_die_das_segment_tragen(clip_ids(pool), info, 8.0)

    assert 4 not in tragende, "der 1.5-s-Schnipsel traegt kein 8-s-Segment"
    # Erwartung aus dem Pool abgeleitet, nicht geschaetzt: genau die Clips,
    # die 8 s (minus 50 ms Toleranz) abdecken.
    assert tragende == [v for v, d in sorted(pool.items()) if d >= 7.95]
    assert kuerzester(pool) == 1.5


@pytest.mark.parametrize("seg_dauer", [1.0, 3.0, 5.0, 11.0, 50.0])
def test_gemischter_pool_liefert_mit_wachsendem_segment_weniger_clips(seg_dauer):
    """Ein realistischer Ordner: je laenger das Segment, desto weniger Kandidaten."""
    info = video_info(POOL_GEMISCHT)
    erwartet = [v for v, d in sorted(POOL_GEMISCHT.items()) if d >= seg_dauer - 0.05]

    tragende = _clips_die_das_segment_tragen(clip_ids(POOL_GEMISCHT), info, seg_dauer)

    if erwartet:
        assert tragende == erwartet
    else:
        # Traegt keiner, bleibt die volle Liste (Fallback).
        assert tragende == clip_ids(POOL_GEMISCHT)


def test_kandidatenzahl_faellt_monoton_mit_der_segmentlaenge():
    """Zusatzpruefung ohne Handzahlen: laengeres Segment -> nie mehr Kandidaten."""
    info = video_info(POOL_GEMISCHT)
    ids = clip_ids(POOL_GEMISCHT)
    zahlen = [len(_clips_die_das_segment_tragen(ids, info, d))
              for d in (1.0, 3.0, 5.0, 11.0)]

    assert zahlen == sorted(zahlen, reverse=True), zahlen


def test_fehlende_dauer_wird_nicht_als_unendlich_gelesen():
    """None oder 0.0 in der Datenbank darf nicht als 'passt immer' durchgehen."""
    info = video_info(POOL_OHNE_DAUER)

    tragende = _clips_die_das_segment_tragen(clip_ids(POOL_OHNE_DAUER), info, 9.5)

    assert tragende == [1], "nur der 10-s-Clip traegt; None und 0.0 fallen raus"


def test_wenn_keiner_traegt_bleibt_die_volle_auswahl():
    info = video_info(POOL_ALLE_ZU_KURZ)

    tragende = _clips_die_das_segment_tragen(clip_ids(POOL_ALLE_ZU_KURZ), info, 30.0)

    assert tragende == clip_ids(POOL_ALLE_ZU_KURZ)


@pytest.mark.parametrize("name", sorted(ALLE_POOLS))
def test_kein_pool_liefert_je_eine_leere_auswahl(name):
    """Eine leere Kandidatenliste wuerde den Segment-Loop ohne Clip lassen."""
    pool = ALLE_POOLS[name]
    info = video_info(pool)

    for seg_dauer in (0.5, 2.0, 7.5, 15.0, 300.0):
        assert _clips_die_das_segment_tragen(clip_ids(pool), info, seg_dauer), (
            f"Pool {name} liefert bei {seg_dauer}s keine Kandidaten"
        )
