"""B-842: Der rote Faden wirkte im tatsächlich benutzten Auswahlpfad nicht.

Befund der Gegenprüfung 2026-08-15. Bogen und Motiv lagen ausschliesslich in
``_match_video_for_segment`` (Legacy-Matcher). Steht ``pacing.use_studio_brain``
auf True — auf der Maschine des Nutzers der Fall —, waehlt aber ``select_best``
ueber ``PacingScorer``, und der Legacy-Matcher laeuft nur als Rueckfall. Im
letzten echten Auto-Edit gab es null Rueckfaelle, also null Segmente ueber den
Bogen.

Die vier Aspekte des roten Fadens hingen damit an zwei sich gegenseitig
ausschliessenden Scorern. Diese Tests halten fest, dass der Term jetzt in
beiden liegt.
"""

from __future__ import annotations

import numpy as np
import pytest

from services.pacing.scorer import (
    DEFAULT_WEIGHTS,
    AudioContext,
    ClipFeatures,
    PacingScorer,
)


def _ctx(**kwargs) -> AudioContext:
    basis = dict(
        at_timestamp_sec=100.0,
        at_beat_idx=200,
        at_section_type="CHORUS",
        at_bpm=132.0,
        at_energy=0.5,
        at_key=None,
        at_key_confidence=None,
        at_harmonic_tension=None,
        at_mood_audio="energetic",
        at_mood_video="energetic",
        at_genre="House",
        at_sub_genre=None,
        at_spectral_hash=None,
        at_groove_template=None,
        at_lufs=None,
    )
    basis.update(kwargs)
    return AudioContext(**basis)


def _clip(clip_id: int, motion: float, bucket: int = 1) -> ClipFeatures:
    return ClipFeatures(
        clip_id=clip_id,
        scene_id=clip_id,
        role="hero",
        mood_refined="energetic",
        style_bucket_id=bucket,
        motion_score=motion,
        embedding=np.zeros(8, dtype=np.float32),
    )


class TestGewichtVorhanden:
    def test_neues_gewicht_ist_registriert(self):
        assert "w_roter_faden" in DEFAULT_WEIGHTS, (
            "ohne Eintrag in DEFAULT_WEIGHTS wird ein Override mit diesem Key "
            "als unbekannt abgelehnt"
        )

    def test_beitrag_bleibt_bescheiden(self):
        """Gemessene Score-Spanne Top1-Top10 liegt bei 0,0325.

        Geprüft wird der BEITRAG, nicht das Gewicht: ``roter_faden_bonus``
        liefert bereits skalierte Werte, das Gewicht ist deshalb — wie bei
        ``w_stem_class`` — ein Faktor 1.0. Ein groesserer Beitrag wuerde die
        Rangfolge bestimmen statt faerben; genau der Fehler der ersten Fassung
        mit 0,12 (Spannweite 0,24 = 7,4-faches der Top-10-Streuung).
        """
        from services.pacing.roter_faden import BOGEN_GEWICHT, MOTIV_GEWICHT

        groesster_beitrag = DEFAULT_WEIGHTS["w_roter_faden"] * (
            BOGEN_GEWICHT + MOTIV_GEWICHT
        )
        assert 0.0 < groesster_beitrag <= 0.06, (
            f"groesster Beitrag {groesster_beitrag:.4f} gegen eine "
            "Top-10-Streuung von 0,0325"
        )


class TestBogenImScorer:
    def _score(self, motion: float, position_sec: float, dauer: float = 200.0) -> float:
        scorer = PacingScorer()
        ctx = _ctx(at_timestamp_sec=position_sec, at_track_duration_sec=dauer)
        gesamt, _ = scorer.score(_clip(1, motion), ctx)
        return gesamt

    def test_am_hoehepunkt_gewinnt_das_kraeftige_bild(self):
        # 75 % von 200 s = 150 s
        kraeftig = self._score(motion=1.0, position_sec=150.0)
        ruhig = self._score(motion=0.1, position_sec=150.0)
        assert kraeftig > ruhig

    def test_am_anfang_gewinnt_das_ruhige_bild(self):
        ruhig = self._score(motion=0.3, position_sec=2.0)
        kraeftig = self._score(motion=1.0, position_sec=2.0)
        assert ruhig > kraeftig

    def test_ohne_trackdauer_ist_der_term_neutral(self):
        """Alt-Aufrufer ohne das neue Feld duerfen sich nicht veraendern."""
        scorer = PacingScorer()
        ctx_ohne = _ctx()
        a, contribs_a = scorer.score(_clip(1, 0.1), ctx_ohne)
        b, contribs_b = scorer.score(_clip(2, 0.9), ctx_ohne)
        assert contribs_a["roter_faden"] == 0.0
        assert contribs_b["roter_faden"] == 0.0

    def test_beitrag_taucht_in_contribs_auf(self):
        scorer = PacingScorer()
        gesamt, contribs = scorer.score(
            _clip(1, 0.8), _ctx(at_timestamp_sec=150.0, at_track_duration_sec=200.0)
        )
        assert "roter_faden" in contribs
        assert abs(sum(contribs.values()) - gesamt) < 1e-9, (
            "der Vertrag sum(contribs) == total muss halten"
        )


class TestMotivImScorer:
    def test_bekannte_bildwelt_gewinnt(self):
        from services.pacing.roter_faden import MotivGedaechtnis

        gedaechtnis = MotivGedaechtnis()
        for _ in range(5):
            gedaechtnis.merken(gruppe=3, style_bucket=7)

        scorer = PacingScorer(motiv_gedaechtnis=gedaechtnis)
        ctx = _ctx(at_timestamp_sec=100.0, at_track_duration_sec=200.0,
                   at_motiv_gruppe=3)
        bekannt, _ = scorer.score(_clip(1, 0.5, bucket=7), ctx)
        fremd, _ = scorer.score(_clip(2, 0.5, bucket=99), ctx)
        assert bekannt > fremd

    def test_ohne_gedaechtnis_neutral(self):
        scorer = PacingScorer()
        ctx = _ctx(at_track_duration_sec=200.0, at_motiv_gruppe=3)
        _, contribs = scorer.score(_clip(1, 0.5, bucket=7), ctx)
        # Nur der Bogen darf beitragen, das Motiv nicht.
        from services.pacing.roter_faden import roter_faden_bonus

        erwartet = DEFAULT_WEIGHTS["w_roter_faden"] * roter_faden_bonus(
            track_position=100.0 / 200.0, clip_intensitaet=0.5,
        )
        assert contribs["roter_faden"] == pytest.approx(erwartet)


class TestVertraegeBleiben:
    def test_batch_entspricht_einzeln(self):
        """Bestandsvertrag: score_batch == score je Clip."""
        scorer = PacingScorer()
        ctx = _ctx(at_timestamp_sec=150.0, at_track_duration_sec=200.0)
        clips = [_clip(i, 0.1 * i) for i in range(1, 6)]
        einzeln = [scorer.score(c, ctx)[0] for c in clips]
        gebatcht = [t for t, _ in scorer.score_batch(clips, ctx)]
        assert einzeln == pytest.approx(gebatcht)

    def test_unbekannter_gewichts_key_wird_weiter_abgelehnt(self):
        with pytest.raises(ValueError):
            PacingScorer(weights={"w_gibt_es_nicht": 0.5})

    def test_bekannter_key_wird_akzeptiert(self):
        scorer = PacingScorer(weights={"w_roter_faden": 0.01})
        assert scorer._weights["w_roter_faden"] == 0.01


class TestImServiceVerdrahtet:
    """Der Term muss in BEIDEN Pfaden ankommen, nicht nur im Legacy-Matcher."""

    def test_service_reicht_die_trackdauer_an_den_kontext(self):
        import inspect

        from services import pacing_service

        quelle = inspect.getsource(pacing_service._auto_edit_phase3_inner)
        assert "track_duration_sec=total_duration" in quelle, (
            "ohne Tracklaenge bleibt der Rote-Faden-Term im Scorer neutral"
        )

    def test_scorer_bekommt_das_gedaechtnis(self):
        import inspect

        from services import pacing_service

        quelle = inspect.getsource(pacing_service._auto_edit_phase3_inner)
        assert "motiv_gedaechtnis=_motiv_gedaechtnis" in quelle, (
            "der Studio-Brain-Scorer teilt das Gedaechtnis nicht"
        )

    def test_studio_brain_pfad_lernt_die_bildwelt(self):
        import inspect

        from services import pacing_service

        quelle = inspect.getsource(pacing_service._auto_edit_phase3_inner)
        stelle = quelle.find("_sb_predecessor = _sb_result.chosen")
        assert stelle > 0
        umfeld = quelle[stelle:stelle + 500]
        assert "_motiv_gedaechtnis.merken" in umfeld, (
            "die Wahl aus select_best landet nicht im Gedaechtnis — dann "
            "bliebe der Motiv-Anteil dauerhaft 0"
        )

    def test_bridge_mapping_leitet_beides_weiter(self):
        import inspect

        from services.pacing import bridge_mapping

        parameter = inspect.signature(bridge_mapping.build_audio_context).parameters
        assert "track_duration_sec" in parameter
        assert parameter["track_duration_sec"].default is None, (
            "der Parameter muss optional sein, sonst brechen Alt-Aufrufer"
        )

        quelle = inspect.getsource(bridge_mapping.build_audio_context)
        assert "at_motiv_gruppe=" in quelle

    def test_motivgruppe_ist_stabil_und_typgebunden(self):
        from services.pacing.bridge_mapping import _motiv_gruppe_aus_typ

        assert _motiv_gruppe_aus_typ("CHORUS") == _motiv_gruppe_aus_typ("chorus")
        assert _motiv_gruppe_aus_typ("CHORUS") != _motiv_gruppe_aus_typ("DROP")
        assert _motiv_gruppe_aus_typ(None) is None
        assert _motiv_gruppe_aus_typ("GIBTESNICHT") is None
