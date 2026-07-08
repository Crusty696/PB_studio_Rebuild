"""NEUBAU-VOLLINTEGRATION T2.5.4: Slice-1-Score-Komponenten im PacingScorer.

Entscheidung (dokumentiert): KOMBINATION statt Ersatz — die neuen Terme
laufen nur, wenn ihre Daten vorliegen (Kurven, Mood-Vektor, Stems);
sonst exakt die Bestands-Funktionen. Alt-Verhalten ohne neue Felder ist
byte-identisch (Golden-Snapshot regeneriert nur um den neutralen
stem_class-Key).
"""
import numpy as np

from services.pacing.scorer import AudioContext, ClipFeatures, PacingScorer


def _ctx(**kw):
    base = dict(
        at_timestamp_sec=10.0, at_beat_idx=4, at_section_type="drop",
        at_bpm=140.0, at_energy=0.8, at_key=None, at_key_confidence=None,
        at_harmonic_tension=0.5, at_mood_audio="energetic",
        at_mood_video="energetic", at_genre=None, at_sub_genre=None,
        at_spectral_hash=None, at_groove_template=None, at_lufs=None,
    )
    base.update(kw)
    return AudioContext(**base)


def _clip(**kw):
    base = dict(clip_id=1, scene_id=1, role="action",
                mood_refined="energetic", style_bucket_id=0,
                motion_score=0.8)
    base.update(kw)
    return ClipFeatures(**base)


class TestFallbackNeutrality:
    def test_without_new_fields_identical_scores(self):
        s = PacingScorer()
        total_a, contribs_a = s.score(_clip(), _ctx())
        total_b, contribs_b = s.score(_clip(), _ctx())
        assert total_a == total_b
        assert contribs_a["stem_class"] == 0.0  # neutral ohne Stems/Shots
        assert abs(sum(contribs_a.values()) - total_a) < 1e-9


class TestStemClassBonus:
    def test_matching_shot_gets_bonus(self):
        s = PacingScorer()
        clip = _clip(shot_confidences={"drum_dominant": 0.9,
                                       "vocal_dominant": 0.05,
                                       "melody_dominant": 0.03,
                                       "bass_dominant": 0.02})
        _, with_match = s.score(clip, _ctx(at_dominant_stem="drums"))
        _, no_match = s.score(clip, _ctx(at_dominant_stem="vocals"))
        assert with_match["stem_class"] == 0.15
        assert no_match["stem_class"] == 0.0


class TestCurveEnergyTerm:
    def test_curves_override_scalar(self):
        s = PacingScorer()
        rms = np.linspace(0, 1, 50)
        motion_aligned = rms.copy()
        motion_anti = 1.0 - rms
        c_al = _clip(motion_curve=motion_aligned)
        c_anti = _clip(motion_curve=motion_anti)
        _, a = s.score(c_al, _ctx(at_rms_curve=rms))
        _, b = s.score(c_anti, _ctx(at_rms_curve=rms))
        assert a["energy"] > b["energy"]  # Kurven-Kohaerenz entscheidet

    def test_missing_curve_falls_back(self):
        s = PacingScorer()
        _, contribs = s.score(_clip(), _ctx(at_rms_curve=np.ones(10)))
        # Clip ohne motion_curve -> skalarer Bestandspfad
        _, base = s.score(_clip(), _ctx())
        assert contribs["energy"] == base["energy"]


class TestMoodVectorTerm:
    def test_vector_alignment_beats_string_match(self):
        s = PacingScorer()
        v = np.zeros(8); v[0] = 1.0
        aligned = _clip(embedding=v.copy())
        anti = _clip(embedding=-v)
        _, a = s.score(aligned, _ctx(at_audio_mood_vec=v))
        _, b = s.score(anti, _ctx(at_audio_mood_vec=v))
        assert a["mood_audio"] > b["mood_audio"]


class TestAudioMoodVecBuilder:
    def test_none_without_stems_or_centroids(self, monkeypatch):
        from services.pacing import bridge_mapping as bm
        assert bm._build_audio_mood_vec(None, "drop") is None
        import services.pacing.shot_centroids as sc
        monkeypatch.setattr(sc, "get_shot_class_centroids", lambda: {})
        assert bm._build_audio_mood_vec(
            {"vocals": 0.5, "drums": 0.5}, "drop") is None

    def test_vec_built_with_centroids(self, monkeypatch):
        from services.pacing import bridge_mapping as bm
        import services.pacing.shot_centroids as sc
        rng = np.random.default_rng(3)
        cents = {k: rng.normal(size=1152).astype(np.float32)
                 for k in ("vocal_dominant", "drum_dominant",
                           "melody_dominant", "bass_dominant")}
        for k, v in cents.items():
            cents[k] = v / np.linalg.norm(v)
        monkeypatch.setattr(sc, "get_shot_class_centroids", lambda: cents)
        vec = bm._build_audio_mood_vec(
            {"vocals": 0.1, "drums": 0.6, "bass": 0.2, "other": 0.1}, "drop")
        assert vec is not None and vec.shape == (1152,)
        assert abs(float(np.linalg.norm(vec)) - 1.0) < 1e-5
