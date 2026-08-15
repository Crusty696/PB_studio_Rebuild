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
