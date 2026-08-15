"""B-840: Pacing-Kurve und Breakdown-Combo waren im neuen Schnitt wirkungslos.

Befund der Gegenprüfung 2026-08-15. Beide Werte werden ausschliesslich in
``_select_cut_beats_advanced`` gelesen — dem Raster-Pfad, der seit der
Umstellung auf ``musikgetriebener_schnitt=True`` faktisch nie mehr läuft.

Damit war es exakt derselbe Fehler wie B-829/B-830/B-831, über den sich der
Nutzer tagelang beschwert hatte ("alles nur Attrappe"), nur eine Ebene tiefer:
die Kurve lässt sich zeichnen, die Combo lässt sich umstellen, und im Ergebnis
ändert sich nichts.

Die Cut-Rate wurde bereits gerettet (``dichte_parameter``). Diese Tests halten
fest, dass Kurve und Breakdown ebenfalls ankommen.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.pacing.roter_faden import schnitt_anlaesse

BPM = 132.0
BEAT = 60.0 / BPM
DAUER = 200.0


def _beats(dauer: float = DAUER) -> list[float]:
    return [i * BEAT for i in range(int(dauer / BEAT))]


def _downbeats(dauer: float = DAUER) -> list[float]:
    return [i * BEAT * 4 for i in range(int(dauer / (BEAT * 4)))]


def _sec(start, ende, typ):
    return SimpleNamespace(start=start, end=ende, section_type=typ)


SECTIONS = [
    _sec(0, 60, "CHORUS"),
    _sec(60, 120, "BREAKDOWN"),
    _sec(120, DAUER, "CHORUS"),
]


def _anzahl(**kwargs) -> int:
    return len(schnitt_anlaesse(
        _beats(), DAUER, sections=SECTIONS, downbeats=_downbeats(), **kwargs
    ))


def _cuts_im_bereich(anlaesse, start, ende) -> int:
    return sum(1 for a in anlaesse if start <= a.zeit < ende)


class TestPacingKurve:
    """Eine gezeichnete Kurve gibt die Dichte über die Zeit vor."""

    def test_kurve_veraendert_das_ergebnis(self):
        ohne = _anzahl()
        dicht = _anzahl(pacing_kurve=[1.0] * 200)
        assert dicht != ohne, (
            f"die gezeichnete Kurve kommt nicht an: ohne={ohne}, mit={dicht}"
        )

    def test_hohe_kurve_schneidet_dichter_als_niedrige(self):
        niedrig = _anzahl(pacing_kurve=[0.05] * 200)
        hoch = _anzahl(pacing_kurve=[1.0] * 200)
        assert hoch > niedrig, (
            f"hohe Dichte muss mehr Schnitte ergeben: {hoch} vs {niedrig}"
        )

    def test_kurve_wirkt_stellenweise(self):
        """Erste Hälfte dicht, zweite ruhig — das muss sich abbilden."""
        kurve = [1.0] * 100 + [0.05] * 100
        anlaesse = schnitt_anlaesse(
            _beats(), DAUER, sections=SECTIONS, downbeats=_downbeats(),
            pacing_kurve=kurve,
        )
        vorne = _cuts_im_bereich(anlaesse, 0, DAUER / 2)
        hinten = _cuts_im_bereich(anlaesse, DAUER / 2, DAUER)
        assert vorne > hinten, (
            f"die Kurve wirkt nicht ortsabhaengig: vorne={vorne}, hinten={hinten}"
        )

    def test_ruhezustand_wirkt_wie_keine_kurve(self):
        """Der flache Ruhezustand [0.5] ist keine Nutzereingabe (B-829)."""
        assert _anzahl(pacing_kurve=None) == _anzahl(pacing_kurve=[0.5] * 200)

    def test_kaputte_kurve_bricht_nicht(self):
        for kurve in ([], [float("nan")] * 200, [-1.0] * 200, [99.0] * 200):
            assert _anzahl(pacing_kurve=kurve) > 0


class TestBreakdownVerhalten:
    """Die Combo steuert, wie ruhig ein Breakdown geschnitten wird."""

    def _im_breakdown(self, verhalten: str) -> int:
        anlaesse = schnitt_anlaesse(
            _beats(), DAUER, sections=SECTIONS, downbeats=_downbeats(),
            breakdown_behavior=verhalten,
        )
        return _cuts_im_bereich(anlaesse, 60, 120)

    def test_die_drei_werte_unterscheiden_sich(self):
        werte = {v: self._im_breakdown(v) for v in ("halve", "force16", "none")}
        assert len(set(werte.values())) > 1, (
            f"alle Breakdown-Werte liefern dasselbe: {werte}"
        )

    def test_halve_schneidet_ruhiger_als_none(self):
        assert self._im_breakdown("halve") < self._im_breakdown("none"), (
            "'halve' soll die Dichte im Breakdown halbieren"
        )

    def test_force16_ist_am_ruhigsten(self):
        force16 = self._im_breakdown("force16")
        assert force16 <= self._im_breakdown("halve"), (
            "'force16' erzwingt den groessten Abstand"
        )

    def test_breakdown_wirkt_nur_im_breakdown(self):
        """Die uebrigen Sections duerfen sich nicht mitveraendern."""
        werte = set()
        for verhalten in ("halve", "force16", "none"):
            anlaesse = schnitt_anlaesse(
                _beats(), DAUER, sections=SECTIONS, downbeats=_downbeats(),
                breakdown_behavior=verhalten,
            )
            werte.add(_cuts_im_bereich(anlaesse, 0, 60))
        assert len(werte) == 1, (
            f"der erste CHORUS aendert sich mit dem Breakdown-Wert: {werte}"
        )

    def test_unbekannter_wert_verhaelt_sich_neutral(self):
        assert self._im_breakdown("unsinn") == self._im_breakdown("none")

    @pytest.mark.parametrize("verhalten", ["halve", "force16", "none"])
    def test_der_breakdown_bleibt_geschnitten(self, verhalten):
        """Auch am ruhigsten darf die Passage kein Standbild werden."""
        assert self._im_breakdown(verhalten) >= 1


class TestImServiceAngeschlossen:
    def test_service_reicht_kurve_und_breakdown_durch(self):
        import inspect

        from services import pacing_service

        quelle = inspect.getsource(pacing_service._auto_edit_phase3_inner)
        assert "pacing_kurve=" in quelle, "die gezeichnete Kurve kommt nicht an"
        assert "breakdown_behavior=" in quelle, "die Breakdown-Combo kommt nicht an"
