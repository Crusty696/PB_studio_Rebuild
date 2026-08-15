"""Cut-Rate und Reaktivität wirken auch im musikgetriebenen Schnitt.

Regression aus meiner eigenen Umstellung (Commit 4403ccd): der neue Pfad
bekam ``base_cut_rate`` gar nicht mehr. Damit war ausgerechnet der Regler
wirkungslos, über den sich der Nutzer tagelang beschwert hatte und der gerade
erst repariert worden war (B-829/B-830/B-835) — nur eine Ebene tiefer.

Die Auflösung: Die Combo bleibt ein Dichte-Regler, aber sie schreibt kein
starres Raster mehr vor. Section-Wechsel und Drops sind von ihr unabhängig und
bilden die Untergrenze; die Combo bestimmt, wie viel **zusätzlich** geschnitten
wird — über die Notbremse (spätestens nach N Takten) und die
Ansprechschwelle für Energiesprünge.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.pacing.roter_faden import (
    ENERGIE_SPRUNG_SCHWELLE,
    MAX_TAKTE_OHNE_SCHNITT,
    dichte_parameter,
    schnitt_anlaesse,
)

BPM = 132.0
BEAT = 60.0 / BPM
DAUER = 240.0
STUFEN = (1, 2, 4, 8, 16)


def _beats(dauer: float = DAUER) -> list[float]:
    return [i * BEAT for i in range(int(dauer / BEAT))]


def _downbeats(dauer: float = DAUER) -> list[float]:
    return [i * BEAT * 4 for i in range(int(dauer / (BEAT * 4)))]


def _sec(start, ende, typ):
    return SimpleNamespace(start=start, end=ende, section_type=typ)


SECTIONS = [
    _sec(0, 40, "BUILDUP"), _sec(40, 90, "CHORUS"), _sec(90, 110, "DROP"),
    _sec(110, 170, "CHORUS"), _sec(170, 200, "BREAKDOWN"), _sec(200, 240, "CHORUS"),
]


class TestDichteParameter:
    def test_vier_beat_ist_der_unveraenderte_mittelwert(self):
        """Die Standardstufe muss das bisherige Verhalten liefern."""
        takte, schwelle = dichte_parameter(base_cut_rate=4, energy_reactivity=50)
        assert takte == MAX_TAKTE_OHNE_SCHNITT
        assert schwelle == pytest.approx(ENERGIE_SPRUNG_SCHWELLE, abs=0.01)

    def test_schnellere_stufe_kuerzt_die_notbremse(self):
        takte_schnell, _ = dichte_parameter(1, 50)
        takte_langsam, _ = dichte_parameter(16, 50)
        assert takte_schnell < MAX_TAKTE_OHNE_SCHNITT < takte_langsam

    def test_notbremse_waechst_monoton_mit_der_stufe(self):
        werte = [dichte_parameter(s, 50)[0] for s in STUFEN]
        for kleiner, groesser in zip(werte, werte[1:]):
            assert groesser > kleiner, f"nicht monoton: {dict(zip(STUFEN, werte))}"

    def test_notbremse_nie_unter_einem_takt(self):
        for stufe in STUFEN:
            assert dichte_parameter(stufe, 50)[0] >= 1

    def test_schnellere_stufe_spricht_auf_kleinere_spruenge_an(self):
        _, schwelle_schnell = dichte_parameter(1, 50)
        _, schwelle_langsam = dichte_parameter(16, 50)
        assert schwelle_schnell < schwelle_langsam, (
            "bei feiner Stufe muss die Energie leichter einen Schnitt ausloesen"
        )

    def test_hohe_reaktivitaet_senkt_die_schwelle(self):
        _, traege = dichte_parameter(4, 0)
        _, mittel = dichte_parameter(4, 50)
        _, flink = dichte_parameter(4, 100)
        assert traege > mittel > flink, (
            f"Reaktivitaet wirkt nicht: {traege:.3f} / {mittel:.3f} / {flink:.3f}"
        )

    def test_schwelle_bleibt_in_sinnvollen_grenzen(self):
        for stufe in STUFEN:
            for reaktivitaet in (0, 25, 50, 75, 100):
                _, schwelle = dichte_parameter(stufe, reaktivitaet)
                assert 0.05 <= schwelle <= 0.9, (
                    f"Stufe {stufe}, Reaktivitaet {reaktivitaet}: {schwelle}"
                )

    def test_unsinnige_eingaben_landen_im_mittelfeld(self):
        for stufe in (0, -3, None):
            takte, schwelle = dichte_parameter(stufe, 50)
            assert takte >= 1 and 0.05 <= schwelle <= 0.9


class TestWirkungAufDieSchnitte:
    def _anzahl(self, stufe: int) -> int:
        takte, schwelle = dichte_parameter(stufe, 50)
        return len(schnitt_anlaesse(
            _beats(), DAUER, sections=SECTIONS,
            energy_per_beat=[0.5] * len(_beats()), downbeats=_downbeats(),
            max_takte=takte, energie_schwelle=schwelle,
        ))

    def test_die_combo_veraendert_das_ergebnis_wirklich(self):
        anzahl = {s: self._anzahl(s) for s in STUFEN}
        assert len(set(anzahl.values())) > 1, (
            f"alle Stufen liefern dasselbe — die Combo waere weiterhin tot: {anzahl}"
        )

    def test_schnellere_stufe_ergibt_mehr_schnitte(self):
        assert self._anzahl(1) > self._anzahl(16), (
            "1 Beat muss dichter schneiden als 16 Beat"
        )

    def test_section_und_drop_bleiben_unabhaengig_von_der_stufe(self):
        """Die Untergrenze darf die Combo nicht unterschreiten koennen.

        Auch auf der langsamsten Stufe muss an jedem Drop geschnitten werden —
        sonst ginge die musikalische Bindung verloren, die der ganze Zweck der
        Umstellung war.
        """
        takte, schwelle = dichte_parameter(16, 50)
        anlaesse = schnitt_anlaesse(
            _beats(), DAUER, sections=SECTIONS, downbeats=_downbeats(),
            max_takte=takte, energie_schwelle=schwelle,
        )
        zeiten = [a.zeit for a in anlaesse]
        for sec in SECTIONS:
            if sec.section_type != "DROP":
                continue
            assert any(abs(z - sec.start) <= BEAT * 4 for z in zeiten), (
                f"DROP bei {sec.start}s fehlt auf der langsamsten Stufe"
            )

    def test_selbst_die_langsamste_stufe_schneidet_noch(self):
        assert self._anzahl(16) >= len(SECTIONS)


class TestAngeschlossenImService:
    def test_service_reicht_die_dichte_durch(self):
        import inspect

        from services import pacing_service

        quelle = inspect.getsource(pacing_service._auto_edit_phase3_inner)
        assert "dichte_parameter" in quelle, (
            "die Cut-Rate erreicht den musikgetriebenen Pfad nicht"
        )
        assert "max_takte=" in quelle and "energie_schwelle=" in quelle

    def test_strategist_laeuft_nicht_ins_leere(self):
        """Sein Ergebnis geht nur in den Raster-Pfad — sonst kostet er umsonst.

        Gemessen am Livelauf vom 15.08.: der Auto-Edit brauchte neun Minuten.
        """
        import inspect

        from services import pacing_service

        quelle = inspect.getsource(pacing_service._auto_edit_phase3_inner)
        stelle = quelle.find("use_llm_strategist")
        assert stelle > 0
        umfeld = quelle[max(0, stelle - 800):stelle + 200]
        assert "musikgetrieben" in umfeld, (
            "der LLM-Strategist wird im musikgetriebenen Modus nicht "
            "uebersprungen, obwohl sein Ergebnis dort niemand liest"
        )
