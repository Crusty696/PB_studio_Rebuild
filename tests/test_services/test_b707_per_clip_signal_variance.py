"""B-707 — Scoring-Terme muessen PRO CLIP variieren, nicht konstant sein.

User-Vorgabe: "es darf keine starre einzelne Regel geben — es muss immer
individuell bei jedem Clip angepasst und ausgesucht werden."

Der Kern dieser Tests ist bewusst VARIANZ, nicht Existenz: die Befunde hatten
gesetzte, plausibel aussehende Werte — sie waren nur fuer jeden Kandidaten
eines Cuts DIESELBEN. Konstante Terme heben sich beim Ranking weg. Ein Test,
der nur "ist gesetzt" prueft, haette keinen der Bugs gefangen.

Abgedeckt:
  Befund 2 — services/brain/reranker.py `_adapt_clip` las contribs-Keys, die
             es nie gab -> 16 von 17 Bridge-Achsen konstant.
  Befund 3 — services/pacing/pipeline.py baute BrainV3Reranker ohne
             brain_weight -> Default 1.0 -> Pacing-Soft-Score verworfen.
  Befund 4 — services/pacing/pattern_lookup.py: genre/key/spectral hart 0.5.

Befund 1 (Scene-Labels aus struct_clip_tags) ist separat als B-728 auf main
gefixt und wird hier nicht dupliziert.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def isolated_appdata(tmp_path: Path, monkeypatch):
    """WeightStore/BrainStore schreiben unter %APPDATA% — pro Test isolieren."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    yield tmp_path


def _spread(values) -> float:
    """max-min ueber eine Werteliste — 0.0 heisst 'konstant'."""
    vals = [float(v) for v in values]
    return max(vals) - min(vals)


# ======================================================================
# Befund 2 — Bridge-Achsen muessen ueber die Kandidaten variieren
# ======================================================================

def _clip_features(clip_id, *, motion, mood, role, bucket, curve_bins, seed):
    from services.pacing.scorer import ClipFeatures

    rng = np.random.default_rng(seed)
    return ClipFeatures(
        clip_id=clip_id,
        scene_id=clip_id * 10,
        role=role,
        mood_refined=mood,
        style_bucket_id=bucket,
        motion_score=motion,
        embedding=rng.standard_normal(32).astype(np.float32),
        motion_curve=np.full(curve_bins, motion, dtype=np.float32),
    )


class _Ctx:
    """Minimaler AudioContext-Stub (der Reranker liest nur getattr)."""
    at_section_type = "drop"
    at_mood_audio = "dramatic"
    at_bpm = 128.0
    at_energy = 0.7
    at_harmonic_tension = 0.4

    def __init__(self, mood_vec=None):
        self.at_audio_mood_vec = mood_vec


def _rerank_axes(brain_weight=1.0, mood_vec=None):
    from services.brain.reranker import BrainV3Reranker
    from services.brain.storage.brain_store import BrainStore
    from services.brain.weight_store import WeightStore

    rr = BrainV3Reranker(WeightStore(BrainStore().weights_path),
                         brain_weight=brain_weight)
    scored = [
        (_clip_features(1, motion=0.15, mood="dark", role="detail",
                        bucket=3, curve_bins=8, seed=1), 0.5, {}),
        (_clip_features(2, motion=0.85, mood="uplifting", role="hero",
                        bucket=7, curve_bins=70, seed=2), 0.5, {}),
        (_clip_features(3, motion=0.50, mood="calm", role="action",
                        bucket=11, curve_bins=35, seed=3), 0.5, {}),
    ]
    return rr.rerank(scored, _Ctx(mood_vec), recent_clip_ids=[99])


def test_b707_2_bridge_axes_vary_across_candidates(isolated_appdata):
    """Vor dem Fix variierte GENAU EINE Achse (motion_match_weight)."""
    out = _rerank_axes(mood_vec=np.ones(32, dtype=np.float32))
    assert len(out) == 3

    axes = out[0].brain_v3_scores.keys()
    varying = {ax for ax in axes
               if _spread([c.brain_v3_scores[ax] for c in out]) > 1e-9}

    expected = {
        "motion_match_weight",    # motion_score
        "min_clip_length",        # Dauer aus motion_curve
        "max_clip_length",        # Dauer aus motion_curve
        "pace_match_weight",      # Dauer aus motion_curve
        "mood_match_weight",      # mood_refined
        "semantic_match_weight",  # Embedding x Audio-Mood-Prototyp
    }
    assert expected <= varying, f"konstant geblieben: {expected - varying}"
    # Regressionsanker: es ist nicht mehr nur motion_match_weight.
    assert len(varying) >= 6


def test_b707_2_adapter_reads_clip_not_contribs(isolated_appdata):
    """_adapt_clip zieht Dauer/Mood/Style aus ClipFeatures, nicht aus contribs."""
    from services.brain.reranker import BrainV3Reranker
    from services.brain.storage.brain_store import BrainStore
    from services.brain.weight_store import WeightStore

    rr = BrainV3Reranker(WeightStore(BrainStore().weights_path))
    a, _ = rr._adapt_clip(
        _clip_features(1, motion=0.2, mood="dark", role="detail", bucket=3,
                       curve_bins=10, seed=1), {})
    b, _ = rr._adapt_clip(
        _clip_features(2, motion=0.9, mood="uplifting", role="hero", bucket=7,
                       curve_bins=60, seed=2), {})

    assert a.duration_s != b.duration_s
    assert a.duration_s == pytest.approx(1.0)   # 10 Bins x 100 ms
    assert b.duration_s == pytest.approx(6.0)   # 60 Bins x 100 ms
    assert a.mood_tags != b.mood_tags
    assert a.style_tags != b.style_tags
    assert a.motion_score != b.motion_score


def test_b707_2_old_contribs_keys_never_existed(isolated_appdata):
    """Regressions-Anker: der alte Adapter las Keys, die der Scorer nie liefert."""
    from services.pacing.scorer import AudioContext, PacingScorer

    ctx = AudioContext(
        at_timestamp_sec=1.0, at_beat_idx=0, at_section_type="drop",
        at_bpm=128.0, at_energy=0.7, at_key=None, at_key_confidence=None,
        at_harmonic_tension=0.4, at_mood_audio="energetic", at_mood_video=None,
        at_genre=None, at_sub_genre=None, at_spectral_hash=None,
        at_groove_template=None, at_lufs=None,
    )
    _, contribs = PacingScorer().score(
        _clip_features(1, motion=0.5, mood="dark", role="hero", bucket=3,
                       curve_bins=10, seed=1), ctx)
    for dead_key in ("brightness", "saturation", "color_temp", "duration_s",
                     "mood_tags", "style_tags"):
        assert dead_key not in contribs


def test_b707_2_axes_without_source_are_marked_no_signal(isolated_appdata):
    """Achsen ohne Quelle werden als 'kein Signal' gemeldet, nicht als 0.5-Note."""
    out = _rerank_axes()  # ohne Audio-Mood-Prototyp
    ns = out[0].no_signal_axes
    # Es gibt keine per-Scene-Bildstatistik im Schema (brightness am
    # Timeline-Clip ist ein Farbkorrektur-Parameter, kein Clip-Merkmal):
    assert "brightness_match_weight" in ns
    assert "color_temp_match_weight" in ns
    # Ohne Audio-Mood-Prototyp kann die semantische Achse nicht bewerten:
    assert "semantic_match_weight" in ns
    # Achsen MIT Signal duerfen nicht als no-signal markiert sein:
    assert "motion_match_weight" not in ns
    assert "pace_match_weight" not in ns
    # Und genau die markierten sind tatsaechlich konstant:
    for axis in ns:
        assert _spread([c.brain_v3_scores[axis] for c in out]) < 1e-9


def test_b707_2_missing_sources_flip_axes_to_no_signal(isolated_appdata):
    """Clip ohne Motion-Kurve/Mood/Embedding: betroffene Achsen ehrlich tot."""
    from services.brain.reranker import BrainV3Reranker
    from services.brain.storage.brain_store import BrainStore
    from services.brain.weight_store import WeightStore
    from services.pacing.scorer import ClipFeatures

    rr = BrainV3Reranker(WeightStore(BrainStore().weights_path))
    bare = ClipFeatures(clip_id=1, scene_id=1, role="unknown",
                        mood_refined="unknown", style_bucket_id=0,
                        motion_score=0.5)
    _, ns = rr._adapt_clip(bare, {})
    assert {"min_clip_length", "max_clip_length", "pace_match_weight",
            "mood_match_weight", "semantic_match_weight"} <= ns


# ======================================================================
# Befund 3 — Pacing-Score muss im Blend wirken
# ======================================================================

def test_b707_3_pipeline_passes_blend_weight(isolated_appdata):
    """PacingPipeline darf den Reranker nicht mit brain_weight=1.0 bauen."""
    from services.pacing.pipeline import DEFAULT_BRAIN_V3_WEIGHT, PacingPipeline

    pipe = PacingPipeline(use_brain_v3=True)
    assert pipe._brain_v3_reranker is not None
    assert pipe._brain_v3_reranker._brain_weight == pytest.approx(
        DEFAULT_BRAIN_V3_WEIGHT)
    assert pipe._brain_v3_reranker._brain_weight < 1.0
    # Konservativ: der eingefahrene Pacing-Score dominiert.
    assert DEFAULT_BRAIN_V3_WEIGHT < 0.5


def test_b707_3_final_score_varies_with_pacing_score(isolated_appdata):
    """Mit dem Blend aendert der Pacing-Soft-Score das Ergebnis — vorher nicht."""
    from services.brain.reranker import BrainV3Reranker
    from services.brain.storage.brain_store import BrainStore
    from services.brain.weight_store import WeightStore
    from services.pacing.pipeline import DEFAULT_BRAIN_V3_WEIGHT

    ws = WeightStore(BrainStore().weights_path)
    # Zwei IDENTISCHE Clips — nur der Pacing-Soft-Score unterscheidet sie.
    a = _clip_features(1, motion=0.7, mood="dark", role="hero", bucket=3,
                       curve_bins=30, seed=1)
    b = _clip_features(2, motion=0.7, mood="dark", role="hero", bucket=3,
                       curve_bins=30, seed=1)
    scored = [(a, 0.2, {}), (b, 1.4, {})]

    blended = BrainV3Reranker(ws, brain_weight=DEFAULT_BRAIN_V3_WEIGHT).rerank(
        scored, _Ctx())
    pure_brain = BrainV3Reranker(ws, brain_weight=1.0).rerank(scored, _Ctx())

    assert _spread([c.final_score for c in pure_brain]) < 1e-9, \
        "brain_weight=1.0 muss den Pacing-Score wegwerfen (Ausgangslage)"
    assert _spread([c.final_score for c in blended]) > 1e-6, \
        "Pacing-Score wirkt nicht im Blend"
    assert blended[0].clip_id == 2  # der besser gepacete Clip gewinnt


def test_b707_3_weight_is_configurable(isolated_appdata, monkeypatch):
    """Der Mischwert ist ein Setting, kein hartkodierter Knopf."""
    from services.pacing.pipeline import DEFAULT_BRAIN_V3_WEIGHT, PacingPipeline

    assert PacingPipeline._resolve_brain_v3_weight(0.42) == pytest.approx(0.42)
    # Ungueltiger Wert -> Default statt Crash
    assert PacingPipeline._resolve_brain_v3_weight(5.0) == pytest.approx(
        DEFAULT_BRAIN_V3_WEIGHT)

    import services.settings_store as ss

    class _Store:
        def get_nested(self, *_args, **_kwargs):
            return 0.15

    monkeypatch.setattr(ss, "get_settings_store", lambda: _Store())
    pipe = PacingPipeline(use_brain_v3=True)
    assert pipe._brain_v3_reranker._brain_weight == pytest.approx(0.15)


# ======================================================================
# Befund 4 — genre/key/spectral-Priors muessen pro Clip variieren
# ======================================================================

def _mem_decision_db(tmp_path):
    """mem_decision mit echtem Nutzer-Feedback — die Quelle der drei Priors."""
    eng = create_engine(f"sqlite:///{(tmp_path / 'mem.db').as_posix()}")
    with eng.begin() as c:
        c.execute(text("""
            CREATE TABLE mem_decision (
                id INTEGER PRIMARY KEY,
                at_genre TEXT,
                at_key TEXT,
                at_spectral_hash TEXT,
                clip_style_bucket_id INTEGER,
                clip_mood_refined TEXT,
                user_verdict TEXT
            )
        """))
        rows = []
        # Style-Bucket 3 / Mood "dark" laufen in Techno gut, 9 / "calm" nicht.
        rows += [("techno", "Am", "h1", 3, "dark", "accept")] * 12
        rows += [("techno", "Am", "h1", 9, "calm", "reject")] * 12
        for genre, key, hsh, bucket, mood, verdict in rows:
            c.execute(text("""
                INSERT INTO mem_decision
                (at_genre, at_key, at_spectral_hash, clip_style_bucket_id,
                 clip_mood_refined, user_verdict)
                VALUES (:g, :k, :h, :b, :m, :v)
            """), {"g": genre, "k": key, "h": hsh, "b": bucket, "m": mood,
                   "v": verdict})

    SessionLocal = sessionmaker(bind=eng)

    @contextmanager
    def factory():
        s = SessionLocal()
        try:
            yield s
        finally:
            s.close()

    return factory


def test_b707_4_genre_prior_varies_per_style_bucket(tmp_path):
    from services.pacing.pattern_lookup import LearnedPatternLookup

    lk = LearnedPatternLookup(_mem_decision_db(tmp_path))
    good = lk("genre", "techno", 3)
    bad = lk("genre", "techno", 9)
    unseen = lk("genre", "techno", 42)

    assert good > bad, f"genre-Prior konstant: {good} vs {bad}"
    assert good > 0.5 and bad < 0.5
    assert unseen == pytest.approx(0.5)  # 0/0 -> ehrlich neutral


def test_b707_4_key_prior_varies_per_clip_mood(tmp_path):
    from services.pacing.pattern_lookup import LearnedPatternLookup

    lk = LearnedPatternLookup(_mem_decision_db(tmp_path))
    assert lk("key", "Am", "dark") > lk("key", "Am", "calm")


def test_b707_4_spectral_prior_varies_per_style_bucket(tmp_path):
    from services.pacing.pattern_lookup import LearnedPatternLookup

    lk = LearnedPatternLookup(_mem_decision_db(tmp_path))
    assert lk("spectral", "h1", 3) > lk("spectral", "h1", 9)


def test_b707_4_no_data_is_flagged_not_faked(tmp_path):
    """Ohne Feedback bleibt es 0.5 — aber sichtbar als 'kein Signal'."""
    from services.pacing.pattern_lookup import LearnedPatternLookup

    lk = LearnedPatternLookup(_mem_decision_db(tmp_path))
    assert lk("genre", "ambient-dub", 3) == pytest.approx(0.5)
    assert "genre" in lk.no_signal_kinds


def test_b707_4_one_query_per_kind_and_context(tmp_path):
    """Kein N+1 im Hot-Loop: 50 Kandidaten -> eine Query."""
    from services.pacing.pattern_lookup import LearnedPatternLookup

    factory = _mem_decision_db(tmp_path)
    calls = {"n": 0}

    @contextmanager
    def counting():
        calls["n"] += 1
        with factory() as s:
            yield s

    lk = LearnedPatternLookup(counting)
    for bucket in range(50):
        lk("genre", "techno", bucket)
    assert calls["n"] == 1


def test_b707_4_scorer_terms_vary(tmp_path):
    """End-to-End: die drei Term-Beitraege unterscheiden zwei Kandidaten."""
    from services.pacing.pattern_lookup import LearnedPatternLookup
    from services.pacing.scorer import AudioContext, ClipFeatures, PacingScorer

    scorer = PacingScorer(
        pattern_lookup=LearnedPatternLookup(_mem_decision_db(tmp_path)))
    ctx = AudioContext(
        at_timestamp_sec=10.0, at_beat_idx=4, at_section_type="drop",
        at_bpm=140.0, at_energy=0.8, at_key="Am", at_key_confidence=0.9,
        at_harmonic_tension=None, at_mood_audio="energetic",
        at_mood_video=None, at_genre="techno", at_sub_genre=None,
        at_spectral_hash="h1", at_groove_template=None, at_lufs=None,
    )

    def clip(bucket, mood):
        return ClipFeatures(clip_id=1, scene_id=bucket, role="action",
                            mood_refined=mood, style_bucket_id=bucket,
                            motion_score=0.5)

    _, good = scorer.score(clip(3, "dark"), ctx)
    _, bad = scorer.score(clip(9, "calm"), ctx)

    assert good["genre"] > bad["genre"]
    assert good["key"] > bad["key"]
    assert good["spectral"] > bad["spectral"]
