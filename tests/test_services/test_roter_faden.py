"""Musikgetriebener Schnitt + roter Faden (User-Anweisung 2026-08-15).

Der Nutzer wollte lange Einstellungen, die nur enden, wenn die Musik einen
Grund liefert — und einen erkennbaren Bogen über die ganze Länge. Ausgangslage
war ein Auto-Edit mit 212 Segmenten auf 337 s (Median 1,37 s).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.pacing.roter_faden import (
    MAX_TAKTE_OHNE_SCHNITT,
    bogen_abweichung,
    bogen_intensitaet,
    motiv_gruppe_fuer_zeit,
    motiv_zuordnung,
    schnitt_anlaesse,
)

BPM = 132.0
BEAT = 60.0 / BPM
DAUER = 337.0


def _beats(dauer: float = DAUER) -> list[float]:
    return [i * BEAT for i in range(int(dauer / BEAT))]


def _downbeats(dauer: float = DAUER) -> list[float]:
    return [i * BEAT * 4 for i in range(int(dauer / (BEAT * 4)))]


def _sec(start, ende, typ):
    return SimpleNamespace(start=start, end=ende, section_type=typ)


# Verkürzte Fassung der echten Struktur aus dem Log vom 15.08.
SECTIONS = [
    _sec(0, 12, "BUILDUP"), _sec(12, 47, "CHORUS"), _sec(47, 54, "VERSE"),
    _sec(54, 69, "BUILDUP"), _sec(69, 81, "CHORUS"), _sec(81, 87, "DROP"),
    _sec(87, 95, "CHORUS"), _sec(95, 103, "BUILDUP"), _sec(103, 107, "DROP"),
    _sec(107, 148, "CHORUS"), _sec(148, 156, "BUILDUP"), _sec(156, 161, "DROP"),
    _sec(161, 168, "CHORUS"), _sec(168, 185, "VERSE"), _sec(185, 197, "BUILDUP"),
    _sec(197, 214, "DROP"), _sec(214, 221, "CHORUS"), _sec(221, 235, "BUILDUP"),
    _sec(235, 245, "CHORUS"), _sec(245, 253, "BUILDUP"), _sec(253, 256, "DROP"),
    _sec(256, 269, "CHORUS"), _sec(269, 273, "DROP"), _sec(273, 296, "CHORUS"),
    _sec(296, 301, "VERSE"), _sec(301, 316, "CHORUS"), _sec(316, 337, "VERSE"),
]


class TestLangeEinstellungen:
    """Der Kernwunsch: deutlich weniger, dafuer laengere Clips."""

    def test_schnittzahl_liegt_im_praxiskorridor(self):
        """Weder hektisch noch traege.

        Der beanstandete Raster-Lauf hatte 212 Schnitte auf 337 s. Eine
        Praxis-Recherche zu Musikvideos ergab als ueblichen Bereich rund
        3-5 s Median, fuer diese Laenge also grob 70-130 Schnitte. Eine
        fruehere Fassung lag mit 31 Schnitten (Median 12,7 s) auf
        Dokumentarfilm-Niveau und damit klar darunter.
        """
        anlaesse = schnitt_anlaesse(
            _beats(), DAUER, sections=SECTIONS, downbeats=_downbeats()
        )
        assert 40 <= len(anlaesse) <= 140, (
            f"{len(anlaesse)} Schnitte auf {DAUER:.0f}s liegen ausserhalb des "
            "Korridors (Raster-Lauf: 212, zu traege Fassung: 31)."
        )

    def test_mittlere_clipdauer_deutlich_ueber_einer_sekunde(self):
        anlaesse = schnitt_anlaesse(
            _beats(), DAUER, sections=SECTIONS, downbeats=_downbeats()
        )
        zeiten = [a.zeit for a in anlaesse] + [DAUER]
        dauern = sorted(b - a for a, b in zip(zeiten, zeiten[1:]))
        median = dauern[len(dauern) // 2]
        assert median >= 3.0, (
            f"Median-Clipdauer {median:.2f}s — der beanstandete Lauf hatte 1,37s."
        )

    def test_ohne_jeden_anlass_greift_die_notbremse(self):
        """Ruhiges Material ohne Sections darf nicht eine Einstellung bleiben."""
        anlaesse = schnitt_anlaesse(_beats(), DAUER, sections=None, downbeats=_downbeats())
        assert len(anlaesse) > 1, "es muss trotzdem geschnitten werden"

        zeiten = [a.zeit for a in anlaesse] + [DAUER]
        groesste_luecke = max(b - a for a, b in zip(zeiten, zeiten[1:]))
        max_erlaubt = BEAT * 4 * MAX_TAKTE_OHNE_SCHNITT
        assert groesste_luecke <= max_erlaubt * 1.3, (
            f"groesste Luecke {groesste_luecke:.1f}s ueberschreitet die Notbremse "
            f"({max_erlaubt:.1f}s) deutlich"
        )


class TestMusikalischeAnlaesse:
    def test_jeder_drop_bekommt_einen_schnitt(self):
        anlaesse = schnitt_anlaesse(
            _beats(), DAUER, sections=SECTIONS, downbeats=_downbeats()
        )
        zeiten = [a.zeit for a in anlaesse]
        toleranz = BEAT * 4
        for sec in SECTIONS:
            if sec.section_type != "DROP":
                continue
            assert any(abs(z - sec.start) <= toleranz for z in zeiten), (
                f"Kein Schnitt am DROP bei {sec.start}s"
            )

    def test_energiesprung_erzeugt_einen_schnitt(self):
        beats = _beats(60.0)
        energie = [0.2] * len(beats)
        sprung_index = 40
        for i in range(sprung_index, len(energie)):
            energie[i] = 0.9

        anlaesse = schnitt_anlaesse(
            beats, 60.0, sections=None, energy_per_beat=energie, downbeats=_downbeats(60.0)
        )
        sprung_zeit = beats[sprung_index]
        assert any(
            a.grund == "energie" and abs(a.zeit - sprung_zeit) <= BEAT * 4
            for a in anlaesse
        ), f"Energiesprung bei {sprung_zeit:.1f}s wurde nicht erkannt"

    def test_gleichmaessige_energie_erzeugt_keine_energie_schnitte(self):
        beats = _beats(60.0)
        anlaesse = schnitt_anlaesse(
            beats, 60.0, sections=None, energy_per_beat=[0.5] * len(beats),
            downbeats=_downbeats(60.0),
        )
        assert not [a for a in anlaesse if a.grund == "energie"], (
            "ohne Sprung darf die Energie keinen Schnitt ausloesen"
        )

    def test_musikalische_anlaesse_liegen_auf_taktanfaengen(self):
        """Section- und Drop-Schnitte muessen auf dem Takt sitzen.

        Fuer Raster-Schnitte (`maximaldauer`) gilt das mit einer Einschraenkung:
        wuerde der Snap auf den Taktanfang den zugesagten Hoechstabstand
        reissen, behaelt die Rohzeit Vorrang. Die Zusage "spaetestens nach N
        Takten" wiegt schwerer als die Optik eines einzelnen Schnitts.
        """
        downbeats = _downbeats()
        anlaesse = schnitt_anlaesse(_beats(), DAUER, sections=SECTIONS, downbeats=downbeats)
        toleranz = BEAT / 2
        daneben = [
            a for a in anlaesse
            if a.grund in ("section", "drop")
            and min(abs(a.zeit - d) for d in downbeats) > toleranz
        ]
        assert not daneben, (
            f"{len(daneben)} musikalische Schnitte liegen nicht auf einem "
            f"Taktanfang: {[(round(a.zeit, 2), a.grund) for a in daneben[:5]]}"
        )

    def test_ergebnis_ist_sortiert_und_doppelungsfrei(self):
        anlaesse = schnitt_anlaesse(
            _beats(), DAUER, sections=SECTIONS,
            energy_per_beat=[0.5] * len(_beats()), downbeats=_downbeats(),
        )
        zeiten = [a.zeit for a in anlaesse]
        assert zeiten == sorted(zeiten)
        for davor, danach in zip(zeiten, zeiten[1:]):
            assert danach - davor >= BEAT * 0.9, (
                f"Zwei Schnitte fast am selben Punkt: {davor:.3f} / {danach:.3f}"
            )

    def test_drop_schlaegt_energie_beim_zusammenfallen(self):
        """Faellt beides zusammen, muss der aussagekraeftigere Grund gewinnen."""
        beats = _beats(60.0)
        energie = [0.2] * len(beats)
        for i in range(int(20 / BEAT), len(energie)):
            energie[i] = 0.9
        sections = [_sec(0, 20, "BUILDUP"), _sec(20, 60, "DROP")]

        anlaesse = schnitt_anlaesse(
            beats, 60.0, sections=sections, energy_per_beat=energie,
            downbeats=_downbeats(60.0),
        )
        nahe = [a for a in anlaesse if abs(a.zeit - 20.0) <= BEAT * 4]
        assert nahe, "am DROP muss ein Schnitt liegen"
        assert any(a.grund == "drop" for a in nahe), (
            f"der Grund sollte 'drop' sein, ist aber {[a.grund for a in nahe]}"
        )

    def test_leere_eingabe(self):
        assert schnitt_anlaesse([], 0.0) == []


class TestDramaturgischerBogen:
    def test_ruhiger_anfang_starke_mitte_ruhiges_ende(self):
        anfang = bogen_intensitaet(0.0)
        hoehepunkt = bogen_intensitaet(0.75)
        ende = bogen_intensitaet(1.0)
        assert anfang < hoehepunkt, "die Mitte muss kraeftiger sein als der Start"
        assert ende < hoehepunkt, "der Schluss muss sich wieder beruhigen"

    def test_steigt_bis_zum_hoehepunkt_monoton(self):
        werte = [bogen_intensitaet(p / 100) for p in range(0, 76)]
        for davor, danach in zip(werte, werte[1:]):
            assert danach >= davor - 1e-9, "der Aufbau darf nicht einbrechen"

    def test_bleibt_im_wertebereich(self):
        for p in (-1.0, 0.0, 0.5, 1.0, 2.0):
            assert 0.0 <= bogen_intensitaet(p) <= 1.0

    def test_abweichung_belohnt_passende_clips(self):
        position = 0.75  # Hoehepunkt
        passend = bogen_abweichung(position, clip_intensitaet=1.0)
        unpassend = bogen_abweichung(position, clip_intensitaet=0.1)
        assert passend < unpassend, (
            "am Hoehepunkt muss ein kraeftiger Clip besser bewertet werden"
        )

    def test_abweichung_ist_null_bei_treffer(self):
        ziel = bogen_intensitaet(0.4)
        assert bogen_abweichung(0.4, ziel) == pytest.approx(0.0)


class TestWiederkehrendeMotive:
    def test_gleicher_section_typ_bekommt_gleiche_gruppe(self):
        zuordnung = motiv_zuordnung(SECTIONS)
        erster_chorus = motiv_gruppe_fuer_zeit(20.0, SECTIONS, zuordnung)
        spaeterer_chorus = motiv_gruppe_fuer_zeit(120.0, SECTIONS, zuordnung)
        assert erster_chorus == spaeterer_chorus, (
            "jeder Refrain muss dieselbe Bildwelt bekommen"
        )

    def test_verschiedene_typen_bekommen_verschiedene_gruppen(self):
        zuordnung = motiv_zuordnung(SECTIONS)
        chorus = motiv_gruppe_fuer_zeit(20.0, SECTIONS, zuordnung)
        drop = motiv_gruppe_fuer_zeit(83.0, SECTIONS, zuordnung)
        assert chorus != drop

    def test_zuordnung_ist_reproduzierbar(self):
        """Zweimal derselbe Track muss dieselbe Zuordnung ergeben."""
        assert motiv_zuordnung(SECTIONS) == motiv_zuordnung(list(reversed(SECTIONS)))

    def test_zeit_ausserhalb_aller_sections(self):
        zuordnung = motiv_zuordnung(SECTIONS)
        assert motiv_gruppe_fuer_zeit(9999.0, SECTIONS, zuordnung) is None

    def test_ohne_sections(self):
        assert motiv_zuordnung(None) == {}
        assert motiv_gruppe_fuer_zeit(5.0, None, {}) is None


class TestBefundeAusDerGegenpruefung:
    """Defekte, die ein Funktionstest mit boesartigen Eingaben fand (2026-08-15).

    Alle vier waren im ersten Wurf enthalten und keiner davon faellt bei
    freundlichen Eingaben auf — genau deshalb stehen sie hier.
    """

    def test_notbremse_wird_nicht_um_25_prozent_ueberschritten(self):
        """Gemessen wurden 20,0s Abstand bei einem Limit von 16,0s.

        Ursache war eine Toleranz von einem Viertel Raster in der
        Lueckenfuellung. Der Fehler zeigt sich nur, wenn ein Anlass NICHT auf
        dem Raster liegt — deshalb der krumme Section-Start.
        """
        bpm = 120.0
        beat = 60.0 / bpm
        dauer = 300.0
        beats = [i * beat for i in range(int(dauer / beat))]
        downbeats = [i * beat * 4 for i in range(int(dauer / (beat * 4)))]
        takt = beat * 4

        for start in (17.0, 19.0, 20.0):
            sections = [_sec(0, start, "CHORUS"), _sec(start, dauer, "CHORUS")]
            anlaesse = schnitt_anlaesse(
                beats, dauer, sections=sections, downbeats=downbeats, max_takte=8
            )
            zeiten = [a.zeit for a in anlaesse] + [dauer]
            groesste = max(b - a for a, b in zip(zeiten, zeiten[1:]))
            assert groesste <= takt * 8 + 1e-6, (
                f"Section-Start {start}s: groesster Abstand {groesste:.2f}s "
                f"ueberschreitet das Limit {takt * 8:.2f}s"
            )

    def test_nan_in_den_beats_wandert_nicht_durch(self):
        """`nan < x` ist immer falsch — NaN faellt sonst durch jede Pruefung."""
        beats = _beats(60.0)
        beats[0] = float("nan")
        anlaesse = schnitt_anlaesse(beats, 60.0, downbeats=_downbeats(60.0))
        assert all(a.zeit == a.zeit for a in anlaesse), (
            f"NaN im Ergebnis: {[a.zeit for a in anlaesse][:5]}"
        )

    def test_unbrauchbare_gesamtdauer_ergibt_nichts(self):
        for dauer in (0.0, -5.0, float("nan"), float("inf")):
            assert schnitt_anlaesse(_beats(60.0), dauer) == [], (
                f"total_duration={dauer} lieferte trotzdem Schnitte"
            )

    def test_kein_schnipsel_am_anfang(self):
        """Der erste Beat liegt bei diesem Material auf 0,04s.

        Zusammen mit der 0.0, die der Aufrufer setzt, entstand daraus ein
        0,04-Sekunden-Segment.
        """
        beats = [0.04 + i * BEAT for i in range(200)]
        anlaesse = schnitt_anlaesse(beats, 90.0, downbeats=_downbeats(90.0))
        assert anlaesse[0].zeit == 0.0, (
            f"erster Schnitt bei {anlaesse[0].zeit}s statt bei 0.0"
        )

    def test_bogen_vertraegt_unbrauchbare_werte(self):
        for wert in (float("nan"), float("inf"), float("-inf"), None, "unsinn"):
            ergebnis = bogen_intensitaet(wert)
            assert 0.0 <= ergebnis <= 1.0, f"{wert!r} ergab {ergebnis}"
