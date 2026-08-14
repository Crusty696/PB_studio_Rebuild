"""B-835: Der Mindestabstand planierte die Cut-Rate-Stufen ein.

Nutzerbefund 2026-08-14: die Pacing-Einstellungen seien "alles nur Attrappe".
Nach den Fixes B-829/B-830/B-831 stimmte zwar die Absicht der Rechnung, das
Ergebnis blieb aber gleich — weil ganz am Ende der Kette
``_enforce_minimum_durations`` die Unterschiede wieder einebnete.

Messung mit der Originalfunktion, 120 s Material, ohne Sections, vor dem Fix::

              1 Beat  2 Beat  4 Beat  8 Beat  16 Beat
    128 BPM      38      33      33      32       16
    100 BPM      41      34      26      25       12
    174 BPM      40      36      30      22       21

Bei 128 BPM — dem Tempobereich, in dem der Nutzer arbeitet — lieferten 2, 4
und 8 Beat praktisch dasselbe. Grund: ``HARD_MIN_DURATION`` stand auf 3,0 s,
und 1/2/4 Beat entsprechen dort 0,47/0,94/1,88 s. Diese Stufen waren physisch
unerreichbar. Mit Sections war es strenger: ``SECTION_MIN_DURATION`` verlangte
für BREAKDOWN und COOLDOWN 6,0 s, womit selbst 8 Beat (3,75 s) ausfiel.

User-Anweisung 2026-08-14: Minimum senken, Section-Minima mitziehen.

Diese Tests halten fest, dass die eingestellte Stufe im Ergebnis ankommt — und
dass der Schutz vor Stotter-Schnitten dabei nicht verlorengeht.
"""

from __future__ import annotations

import logging

import pytest

from services.pacing_beat_grid import HARD_MIN_DURATION, SECTION_MIN_DURATION
from services.pacing_edit_helpers import _enforce_minimum_durations

logging.disable(logging.INFO)

DAUER = 120.0
STUFEN = (1, 2, 4, 8, 16)


def _cuts_fuer_stufe(bpm: float, beats_pro_cut: int, sections=None) -> list[float]:
    """Gleichmässige Cut-Zeiten für eine Cut-Rate-Stufe, dann gefiltert."""
    abstand = (60.0 / bpm) * beats_pro_cut
    zeiten = [i * abstand for i in range(int(DAUER / abstand))]
    return _enforce_minimum_durations(zeiten, sections, DAUER)


class TestStufenBleibenUnterscheidbar:
    @pytest.mark.parametrize("bpm", [128.0, 100.0, 174.0])
    def test_jede_stufe_liefert_eine_eigene_cut_zahl(self, bpm):
        anzahl = {s: len(_cuts_fuer_stufe(bpm, s)) for s in STUFEN}
        assert len(set(anzahl.values())) == len(STUFEN), (
            f"B-835: bei {bpm} BPM liefern verschiedene Cut-Rate-Stufen dieselbe "
            f"Cut-Zahl — die Einstellung kommt nicht im Ergebnis an: {anzahl}"
        )

    @pytest.mark.parametrize("bpm", [128.0, 100.0, 174.0])
    def test_schneller_eingestellt_heisst_mehr_schnitte(self, bpm):
        """Monotonie: 1 Beat muss mehr Cuts liefern als 2, 2 mehr als 4 …"""
        anzahl = [len(_cuts_fuer_stufe(bpm, s)) for s in STUFEN]
        for schneller, langsamer in zip(anzahl, anzahl[1:]):
            assert schneller > langsamer, (
                f"B-835: bei {bpm} BPM ist die Reihenfolge verletzt: {anzahl}"
            )

    def test_128bpm_livebefund_2_4_8_beat_trennen_sich(self):
        """Der konkrete Fall aus dem Nutzerbefund: vorher 33/33/32."""
        zwei = len(_cuts_fuer_stufe(128.0, 2))
        vier = len(_cuts_fuer_stufe(128.0, 4))
        acht = len(_cuts_fuer_stufe(128.0, 8))
        assert zwei > vier > acht, (
            f"B-835: 2/4/8 Beat bei 128 BPM liefern {zwei}/{vier}/{acht} — "
            "vorher waren es 33/33/32."
        )


class TestSchutzBleibtBestehen:
    """Das Minimum darf sinken, aber nicht verschwinden."""

    def test_kein_segment_unter_dem_harten_minimum(self):
        """Der letzte Cut ist ausgenommen — er steht per Design in ``protected``
        (``pacing_edit_helpers.py:369``: Start und Ende werden nie entfernt) und
        darf deshalb ein kuerzeres Restsegment erzeugen."""
        for bpm in (128.0, 100.0, 174.0):
            for stufe in STUFEN:
                cuts = _cuts_fuer_stufe(bpm, stufe)
                for davor, danach in zip(cuts[:-2], cuts[1:-1]):
                    assert danach - davor >= HARD_MIN_DURATION - 1e-9, (
                        f"B-835: {bpm} BPM, {stufe} Beat — Segment "
                        f"{danach - davor:.3f}s unterschreitet das Minimum "
                        f"{HARD_MIN_DURATION}s."
                    )

    def test_minimum_ist_nicht_abgeschaltet(self):
        assert HARD_MIN_DURATION > 0, (
            "ein Minimum von 0 wuerde Stotter-Schnitte erlauben"
        )

    def test_ein_beat_wird_weiterhin_ausgeduennt(self):
        """1 Beat bei 128 BPM sind 0,47s — das muss gefiltert werden."""
        roh = int(DAUER / (60.0 / 128.0))
        gefiltert = len(_cuts_fuer_stufe(128.0, 1))
        assert gefiltert < roh, (
            "die schnellste Stufe darf nicht ungefiltert durchlaufen"
        )


class TestSectionCharakteristikBleibt:
    """Die Sections behalten ihre relative Ordnung: DROP schnell, BREAKDOWN ruhig."""

    def test_drop_darf_schneller_schneiden_als_breakdown(self):
        assert SECTION_MIN_DURATION["DROP"] < SECTION_MIN_DURATION["BREAKDOWN"]

    @pytest.mark.parametrize("bpm", [128.0, 174.0])
    def test_minimum_blockiert_nie_die_eigene_schnellste_stufe(self, bpm):
        """Der eigentliche Vertrag.

        ``SECTION_PACING_MAP`` legt pro Section fest, welche Cut-Stufen
        vorgesehen sind — ``min`` ist die schnellste erlaubte, in Beats. Ein
        Mindestabstand, der genau diese Stufe verbietet, macht die Vorgabe
        wirkungslos. Vorher war das bei fast jeder Section der Fall: BREAKDOWN
        durfte laut Map ab 8 Beat schneiden (3,75s bei 128 BPM), verlangte aber
        6,0s Mindestabstand.
        """
        from services.pacing_beat_grid import SECTION_PACING_MAP

        beatlaenge = 60.0 / bpm
        for name, minimum in SECTION_MIN_DURATION.items():
            vorgabe = SECTION_PACING_MAP.get(name)
            if not vorgabe:
                continue
            schnellste = vorgabe["min"] * beatlaenge
            assert minimum <= schnellste + 1e-9, (
                f"B-835: Section {name} laesst laut SECTION_PACING_MAP "
                f"{vorgabe['min']} Beat zu ({schnellste:.2f}s bei {bpm} BPM), "
                f"verlangt aber {minimum}s Mindestabstand — die Stufe ist "
                "damit unerreichbar."
            )

    def test_sections_bleiben_untereinander_verschieden(self):
        """Wenn alle Sections dasselbe Minimum haetten, waere die Struktur weg."""
        assert len(set(SECTION_MIN_DURATION.values())) > 1

    def test_ordnung_wurde_nicht_invertiert(self):
        """Ruhige Sections muessen ruhig bleiben, schnelle schnell.

        Die exakte Rangfolge darf sich verschieben — BUILDUP zieht mit DROP
        gleich, weil SECTION_PACING_MAP beiden dieselbe schnellste Stufe
        einraeumt. Was nicht passieren darf, ist eine Umkehr.
        """
        schnell = ("DROP", "BUILDUP", "CHORUS")
        ruhig = ("BREAKDOWN", "COOLDOWN", "WARMUP")
        groesstes_schnelles = max(SECTION_MIN_DURATION[s] for s in schnell)
        kleinstes_ruhiges = min(SECTION_MIN_DURATION[s] for s in ruhig)
        assert groesstes_schnelles < kleinstes_ruhiges, (
            "B-835: eine schnelle Section verlangt jetzt mehr Mindestabstand "
            "als eine ruhige — die Charakteristik waere verdreht."
        )

    def test_werte_stimmen_mit_der_dokumentierten_herleitung(self):
        """Gegenprobe zur Kommentar-Formel: min-Beats x 174-BPM-Beat, -5 %."""
        from services.pacing_beat_grid import SECTION_PACING_MAP

        beatlaenge_174 = 60.0 / 174.0
        for name, minimum in SECTION_MIN_DURATION.items():
            vorgabe = SECTION_PACING_MAP.get(name)
            if not vorgabe:
                continue
            erwartet = vorgabe["min"] * beatlaenge_174 * 0.95
            assert abs(minimum - erwartet) < 0.05, (
                f"B-835: {name} steht auf {minimum}s, die dokumentierte "
                f"Herleitung ergibt {erwartet:.2f}s. Kommentar und Wert "
                "muessen zusammenpassen."
            )
