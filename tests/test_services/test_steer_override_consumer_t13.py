"""NEUBAU-VOLLINTEGRATION T1.3 (USE-004): SteerOverrideQueue-Consumer.

Vorher: UI schrieb die Queue (steer_tab/structure_tab), kein Backend las —
Boost/Exclude waren wirkungslos ("the consumer (pacing agent) ships later").
Jetzt: Boost -> STEER_BOOST_BONUS in PacingPipeline.select_best, Exclude ->
harter Kandidaten-Ausschluss in pacing_service, Drain nach Lauf.
"""
import numpy as np

from services.pacing.pipeline import PacingPipeline, STEER_BOOST_BONUS
from services.pacing.scorer import AudioContext, ClipFeatures, PacingScorer


def _ctx(t=10.0):
    return AudioContext(
        at_timestamp_sec=t, at_beat_idx=4, at_section_type="drop",
        at_bpm=140.0, at_energy=0.8, at_key=None, at_key_confidence=None,
        at_harmonic_tension=None, at_mood_audio="energetic",
        at_mood_video=None, at_genre=None, at_sub_genre=None,
        at_spectral_hash=None, at_groove_template=None, at_lufs=None,
    )


def _clip(clip_id, scene_id, motion=0.5):
    return ClipFeatures(
        clip_id=clip_id, scene_id=scene_id, role="action",
        mood_refined="energetic", style_bucket_id=1, motion_score=motion,
        embedding=None,
    )


class TestBoostInSelectBest:
    def test_boost_flips_winner(self):
        """Zwei fast identische Kandidaten: Boost auf den schwaecheren
        muss die Wahl kippen (Bonus 0.5 >> Motion-Differenz)."""
        p = PacingPipeline(scorer=PacingScorer())
        strong = _clip(1, 101, motion=0.9)
        weak = _clip(2, 202, motion=0.8)

        r_plain = p.select_best([strong, weak], _ctx())
        assert r_plain.chosen is not None

        p2 = PacingPipeline(scorer=PacingScorer())
        r_boost = p2.select_best(
            [strong, weak], _ctx(), boost_scene_ids={202},
        )
        assert r_boost.chosen is not None
        assert r_boost.chosen.clip_id == 2

    def test_boost_contrib_recorded(self):
        p = PacingPipeline(scorer=PacingScorer())
        r = p.select_best([_clip(1, 101)], _ctx(), boost_scene_ids={101})
        assert r.chosen is not None
        # Rationale enthaelt den steer_boost-Beitrag
        found = False
        for sr in r.rationale.get("stage_results", []):
            contribs = sr.get("contribs") if isinstance(sr, dict) else None
            if contribs and abs(
                    contribs.get("steer_boost", 0.0) - STEER_BOOST_BONUS
            ) < 1e-9:
                found = True
        assert found

    def test_no_boost_is_neutral(self):
        """Ohne boost_scene_ids identisches Verhalten wie vorher
        (Rueckwaertskompatibilitaet der Signatur)."""
        p1 = PacingPipeline(scorer=PacingScorer())
        p2 = PacingPipeline(scorer=PacingScorer())
        cands = [_clip(1, 101, 0.9), _clip(2, 202, 0.3)]
        r1 = p1.select_best(cands, _ctx())
        r2 = p2.select_best(cands, _ctx(), boost_scene_ids=None)
        assert r1.chosen.clip_id == r2.chosen.clip_id


class TestQueueContract:
    def test_queue_roundtrip_and_drain(self):
        from services.steer_override_queue import (
            SteerOverrideQueue,
        )
        q = SteerOverrideQueue()
        q.add(101, "boost", "test")
        q.add(202, "exclude", "test")
        boost, exclude = set(), set()
        for ov in q.list():
            (boost if ov.action == "boost" else exclude).add(int(ov.scene_id))
        assert boost == {101} and exclude == {202}
        q.clear()
        assert q.count() == 0


def test_product_wiring_present():
    """Quelltext-Vertrag: pacing_service liest die Queue, filtert Excludes,
    reicht Boosts an select_best durch und draint nach dem Lauf."""
    import inspect

    import services.pacing_service as ps
    src = inspect.getsource(ps)
    assert "from services.steer_override_queue import get_default_queue" in src
    assert "boost_scene_ids=_steer_boost or None" in src
    assert "_steer_exclude" in src
    assert src.count("get_default_queue().clear()") >= 1
