"""B-838: Pflicht-Cuts unterliefen die zuvor erzwungene Mindestdauer.

Befund aus dem Funktionstest 2026-08-15. Die Reihenfolge im Auto-Edit ist:

    1. ``_enforce_minimum_durations``  — entfernt zu kurze Segmente
    2. ``finalize_cut_beats``          — fügt Pflicht-Cuts an Section-Grenzen ein

Schritt 2 setzt danach 26 zusätzliche Cuts, ohne die Mindestdauer erneut zu
prüfen. Gemessen am echten Projekt: von 78 Segmenten lagen anschliessend **37
unter 3,0 s**, das kürzeste bei 0,90 s — obwohl Schritt 1 genau das verhindern
sollte.

Verschärft wurde es durch B-835: ``finalize_cut_beats`` schützt Pflicht-Cuts
über ``HARD_MIN_DURATION * 0.6``. Mit dem alten Wert 3,0 waren das 1,8 s
Schutzzone, mit dem neuen 1,0 nur noch 0,6 s — zu wenig, um benachbarte
Raster-Cuts zu verdrängen.

Section-Grenzen bleiben unantastbar: ein Schnitt am Drop-Einstieg ist der Sinn
der ganzen Übung. Entfernt werden nur die **nicht** verpflichtenden Cuts, die
zu dicht daneben liegen.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

from services.pacing_beat_grid import HARD_MIN_DURATION, SECTION_MIN_DURATION
from services.pacing_edit_helpers import finalize_cut_beats

logging.disable(logging.INFO)

BPM = 132.0
BEAT = 60.0 / BPM
DAUER = 240.0


def _beats(dauer: float = DAUER) -> list[float]:
    return [i * BEAT for i in range(int(dauer / BEAT) + 1)]


def _downbeats(dauer: float = DAUER) -> list[float]:
    return [i * BEAT * 4 for i in range(int(dauer / (BEAT * 4)) + 1)]


def _sec(start, ende, typ):
    return SimpleNamespace(start=start, end=ende, section_type=typ)


# Section-Grenzen bewusst NICHT auf dem Raster, damit die Pflicht-Cuts
# zwischen die vorhandenen Cuts fallen — genau der Fall aus dem Livelauf.
SECTIONS = [
    _sec(0, 37.3, "BUILDUP"), _sec(37.3, 81.7, "CHORUS"),
    _sec(81.7, 95.2, "DROP"), _sec(95.2, 140.4, "CHORUS"),
    _sec(140.4, 168.9, "BREAKDOWN"), _sec(168.9, DAUER, "CHORUS"),
]


def _segmentdauern(cuts: list[float]) -> list[float]:
    return [b - a for a, b in zip(cuts, cuts[1:])]


def _mindestdauer_an(zeit: float) -> float:
    for sec in SECTIONS:
        if sec.start <= zeit < sec.end:
            return SECTION_MIN_DURATION.get(sec.section_type, HARD_MIN_DURATION)
    return HARD_MIN_DURATION


class TestMindestdauerUeberlebtFinalize:
    def _cuts(self) -> list[float]:
        # Gleichmässiges 2-Takt-Raster, wie es der musikgetriebene Schnitt
        # liefert — alle Abstände über der Mindestdauer.
        raster = BEAT * 8
        roh = [i * raster for i in range(int(DAUER / raster) + 1)]
        return finalize_cut_beats(roh, _beats(), _downbeats(), SECTIONS, DAUER)

    def test_kein_segment_unter_der_mindestdauer(self):
        cuts = self._cuts()
        zu_kurz = [
            (round(a, 2), round(b - a, 2), round(_mindestdauer_an(a), 2))
            for a, b in zip(cuts, cuts[1:])
            if (b - a) < _mindestdauer_an(a) - 1e-6
        ]
        assert not zu_kurz, (
            f"B-838: {len(zu_kurz)} Segmente unterschreiten die Mindestdauer "
            f"trotz vorheriger Pruefung: {zu_kurz[:6]}"
        )

    def test_kein_segment_unter_dem_kleinsten_section_minimum(self):
        """Die Untergrenze ist das kleinste Section-Minimum, nicht HARD_MIN.

        ``SECTION_MIN_DURATION`` ist seit B-835 autoritativ und liegt bewusst
        unter ``HARD_MIN_DURATION``: ein DROP darf mit 0,33 s dichter schneiden
        als das globale Minimum von 1,0 s erlauben würde. Ein Segment von
        0,91 s in einem BUILDUP ist deshalb korrekt, nicht defekt.
        """
        cuts = self._cuts()
        kuerzestes = min(_segmentdauern(cuts))
        untergrenze = min(SECTION_MIN_DURATION.values())
        assert kuerzestes >= untergrenze - 1e-6, (
            f"B-838: kuerzestes Segment {kuerzestes:.2f}s liegt unter dem "
            f"kleinsten Section-Minimum {untergrenze}s"
        )

    def test_section_grenzen_bleiben_erhalten(self):
        """Der Sinn der Pflicht-Cuts darf nicht wegoptimiert werden."""
        cuts = self._cuts()
        for sec in SECTIONS:
            if sec.start <= 0.05 or sec.start >= DAUER - 0.05:
                continue
            assert any(abs(c - sec.start) <= BEAT * 2 for c in cuts), (
                f"B-838: Section-Grenze {sec.start}s ({sec.section_type}) hat "
                "keinen Cut mehr — das Ausduennen ging zu weit."
            )

    def test_rahmen_bleibt_exakt(self):
        cuts = self._cuts()
        assert cuts[0] == 0.0
        assert abs(cuts[-1] - DAUER) < 0.01

    def test_cuts_bleiben_sortiert_und_eindeutig(self):
        cuts = self._cuts()
        assert cuts == sorted(cuts)
        assert len(cuts) == len(set(cuts))


class TestDichtesRasterWirdAusgeduennt:
    """Der harte Fall: ein Raster feiner als die Mindestdauer."""

    def test_sehr_dichtes_raster_wird_auf_die_mindestdauer_gebracht(self):
        """Ein Cut auf JEDEM Beat (0,45 s) muss ausgeduennt werden."""
        eng = [i * BEAT for i in range(int(DAUER / BEAT))]
        cuts = finalize_cut_beats(eng, _beats(), _downbeats(), SECTIONS, DAUER)
        zu_kurz = [
            (round(a, 2), round(b - a, 2))
            for a, b in zip(cuts, cuts[1:])
            if (b - a) < _mindestdauer_an(a) - 1e-6
        ]
        assert not zu_kurz, (
            f"{len(zu_kurz)} Segmente unter dem Section-Minimum: {zu_kurz[:6]}"
        )
        assert min(_segmentdauern(cuts)) >= min(SECTION_MIN_DURATION.values()) - 1e-6

    def test_ohne_sections_gilt_das_harte_minimum(self):
        eng = [i * BEAT for i in range(int(DAUER / BEAT))]
        cuts = finalize_cut_beats(eng, _beats(), _downbeats(), None, DAUER)
        assert min(_segmentdauern(cuts)) >= HARD_MIN_DURATION - 1e-6


class TestSplitVertraegtSichMitDerMindestdauer:
    def test_max_segment_split_erzeugt_keine_schnipsel(self):
        """Der Split gegen die Cliplänge darf keine Kurzsegmente hinterlassen."""
        roh = [0.0, DAUER]
        cuts = finalize_cut_beats(
            roh, _beats(), _downbeats(), SECTIONS, DAUER,
            max_segment_duration=10.0,
        )
        kuerzestes = min(_segmentdauern(cuts))
        assert kuerzestes >= HARD_MIN_DURATION - 1e-6, (
            f"Split hinterliess ein {kuerzestes:.2f}s-Segment"
        )
        assert max(_segmentdauern(cuts)) <= 10.0 + 0.5, (
            "der Split haelt die Obergrenze nicht ein"
        )
