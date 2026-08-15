"""Der rote Faden in der echten Kette (User-Anweisung 2026-08-15).

Ergänzt ``test_roter_faden.py`` (Bausteine einzeln) um den Nachweis, dass die
Bausteine auch angeschlossen sind: Schalter in ``AdvancedPacingSettings``,
Umschaltung in ``pacing_service`` und die angehobenen Scorer-Gewichte.
"""

from __future__ import annotations

from services.pacing.scorer import DEFAULT_WEIGHTS
from services.pacing_beat_grid import AdvancedPacingSettings


class TestSchalter:
    def test_musikgetriebener_schnitt_ist_standard(self):
        """Der Nutzer wollte es so eingestellt haben, nicht als Option."""
        assert AdvancedPacingSettings().musikgetriebener_schnitt is True

    def test_roter_faden_ist_standard(self):
        assert AdvancedPacingSettings().roter_faden is True

    def test_raster_pfad_bleibt_abschaltbar(self):
        """Der alte Weg muss erreichbar bleiben — er ist der Rueckfallweg."""
        s = AdvancedPacingSettings(musikgetriebener_schnitt=False)
        assert s.musikgetriebener_schnitt is False

    def test_uebrige_vorgaben_unveraendert(self):
        """Gegenprobe: die neuen Felder haben nichts anderes verschoben."""
        s = AdvancedPacingSettings()
        assert s.base_cut_rate == 4
        assert s.energy_reactivity == 50
        assert s.breakdown_behavior == "halve"
        assert s.transition_type == "cut"


class TestUmschaltungImService:
    def test_service_kennt_beide_wege(self):
        """Beide Zweige muessen im Quelltext vorhanden sein."""
        import inspect

        from services import pacing_service

        quelle = inspect.getsource(pacing_service._auto_edit_phase3_inner)
        assert "musikgetriebener_schnitt" in quelle, (
            "die Umschaltung fehlt — der Schalter waere wirkungslos"
        )
        assert "schnitt_anlaesse" in quelle, "der neue Weg ist nicht angeschlossen"
        assert "_select_cut_beats_advanced" in quelle, (
            "der Raster-Pfad wurde entfernt statt nur umgangen"
        )

    def test_getattr_absicherung(self):
        """Aeltere Settings-Objekte ohne das Feld duerfen nicht abstuerzen.

        Der Auto-Edit bekommt Settings aus mehreren Quellen (UI, Profil,
        LLM-Strategist). Ein Objekt ohne das neue Feld muss auf dem alten Weg
        landen statt eine AttributeError zu werfen.
        """
        import inspect

        from services import pacing_service

        quelle = inspect.getsource(pacing_service._auto_edit_phase3_inner)
        assert 'getattr(settings, "musikgetriebener_schnitt"' in quelle


class TestKohaerenzGewichte:
    """Weiche Uebergaenge und weniger Wiederholungen — beides ueber Gewichte."""

    def test_stil_aehnlichkeit_wiegt_schwerer_als_frueher(self):
        assert DEFAULT_WEIGHTS["w_style"] > 0.15, (
            "w_style entscheidet, wie gut zwei benachbarte Clips zusammenpassen"
        )

    def test_stilbruch_wiegt_schwerer_als_frueher(self):
        assert DEFAULT_WEIGHTS["w_collision"] > 0.10

    def test_wiederholung_wiegt_schwerer_als_frueher(self):
        assert DEFAULT_WEIGHTS["w_freshness"] > 0.05, (
            "im Lauf vom 15.08. kamen 102 von 110 Clips doppelt vor"
        )

    def test_uebergangs_terme_schlagen_die_rolle_nicht_tot(self):
        """Kohaerenz ja, aber die Rollenpassung bleibt der staerkste Einzelterm.

        Sonst wuerde die Auswahl nur noch Aehnlichkeit optimieren und immer
        dieselbe Sorte Bild liefern — das waere kein roter Faden mehr, sondern
        Monotonie.
        """
        assert DEFAULT_WEIGHTS["w_style"] <= DEFAULT_WEIGHTS["w_role"] + 0.05

    def test_alle_gewichte_bleiben_positiv(self):
        for name, wert in DEFAULT_WEIGHTS.items():
            assert wert >= 0.0, f"{name} ist negativ: {wert}"


class TestBogenUndMotiveVerdrahtet:
    """Die zwei Aspekte, die im ersten Wurf nur gebaut, aber nicht
    angeschlossen waren (offen gemeldet, jetzt nachgezogen)."""

    def test_bonus_bevorzugt_kraeftige_bilder_am_hoehepunkt(self):
        from services.pacing.roter_faden import roter_faden_bonus

        kraeftig = roter_faden_bonus(track_position=0.75, clip_intensitaet=1.0)
        ruhig = roter_faden_bonus(track_position=0.75, clip_intensitaet=0.1)
        assert kraeftig > ruhig

    def test_bonus_bevorzugt_ruhige_bilder_am_anfang(self):
        from services.pacing.roter_faden import roter_faden_bonus

        ruhig = roter_faden_bonus(track_position=0.0, clip_intensitaet=0.3)
        kraeftig = roter_faden_bonus(track_position=0.0, clip_intensitaet=1.0)
        assert ruhig > kraeftig

    def test_ohne_angaben_ist_der_bonus_null(self):
        """Alt-Aufrufer duerfen sich nicht veraendern."""
        from services.pacing.roter_faden import roter_faden_bonus

        assert roter_faden_bonus(track_position=0.5, clip_intensitaet=None) == 0.0

    def test_motiv_gedaechtnis_belohnt_die_bildwelt_der_gruppe(self):
        from services.pacing.roter_faden import MotivGedaechtnis, roter_faden_bonus

        g = MotivGedaechtnis()
        for _ in range(3):
            g.merken(gruppe=1, style_bucket=7)

        bekannt = roter_faden_bonus(0.5, None, motiv_gruppe=1, style_bucket=7, gedaechtnis=g)
        fremd = roter_faden_bonus(0.5, None, motiv_gruppe=1, style_bucket=99, gedaechtnis=g)
        assert bekannt > fremd, "die wiederkehrende Bildwelt muss gewinnen"

    def test_motiv_gedaechtnis_bestraft_nie(self):
        """Ein Malus wuerde die erste Wahl einer Gruppe alle weiteren blockieren."""
        from services.pacing.roter_faden import MotivGedaechtnis, roter_faden_bonus

        g = MotivGedaechtnis()
        g.merken(gruppe=1, style_bucket=7)
        assert roter_faden_bonus(0.5, None, motiv_gruppe=1, style_bucket=99, gedaechtnis=g) >= 0.0

    def test_verschiedene_gruppen_bleiben_getrennt(self):
        from services.pacing.roter_faden import MotivGedaechtnis

        g = MotivGedaechtnis()
        g.merken(gruppe=1, style_bucket=7)
        assert g.passt_zur_gruppe(2, 7) == 0.0

    def test_gedaechtnis_vertraegt_none(self):
        from services.pacing.roter_faden import MotivGedaechtnis

        g = MotivGedaechtnis()
        g.merken(None, 5)
        g.merken(1, None)
        assert g.passt_zur_gruppe(None, None) == 0.0

    def test_auswahl_nimmt_die_neuen_parameter_entgegen(self):
        import inspect

        from services.pacing_edit_helpers import _match_video_for_segment

        parameter = inspect.signature(_match_video_for_segment).parameters
        for name in ("track_position", "motiv_gruppe", "motiv_gedaechtnis"):
            assert name in parameter, f"{name} fehlt in der Auswahl"
            assert parameter[name].default is None, (
                f"{name} muss optional sein, sonst brechen Alt-Aufrufer"
            )

    def test_service_fuettert_die_parameter(self):
        import inspect

        from services import pacing_service

        quelle = inspect.getsource(pacing_service._auto_edit_phase3_inner)
        assert "track_position=" in quelle
        assert "motiv_gedaechtnis=" in quelle
        assert "MotivGedaechtnis()" in quelle
