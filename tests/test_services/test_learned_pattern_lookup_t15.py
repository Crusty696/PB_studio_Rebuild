"""NEUBAU-VOLLINTEGRATION T1.5 (USE-008): Lernschleife geschlossen.

mem_learned_pattern (PatternAggregator) wird jetzt vom produktiven
PacingScorer ueber LearnedPatternLookup gelesen — w_memory-Term reagiert
auf gelernte Accept/Reject-Statistiken statt dauerhaft neutral zu sein.
"""
import json
from contextlib import contextmanager

from sqlalchemy import create_engine, text

from services.pacing.pattern_lookup import LearnedPatternLookup


def _make_db(tmp_path):
    eng = create_engine(f"sqlite:///{(tmp_path / 'mem.db').as_posix()}")
    with eng.begin() as c:
        c.execute(text("""
            CREATE TABLE mem_learned_pattern (
                id INTEGER PRIMARY KEY,
                pattern_type TEXT,
                context_fingerprint TEXT,
                target_ref TEXT,
                stat_accept_count INTEGER,
                stat_reject_count INTEGER,
                stat_sample_size INTEGER,
                confidence REAL,
                last_updated TEXT
            )
        """))
        c.execute(text("""
            INSERT INTO mem_learned_pattern
            (pattern_type, context_fingerprint, target_ref,
             stat_accept_count, stat_reject_count, stat_sample_size,
             confidence, last_updated)
            VALUES ('context_preference', :fp, :tr, 18, 2, 20, 0.7, '2026-07-08')
        """), {
            "fp": json.dumps({"genre": "techno", "section_type": "drop",
                              "bpm_bucket": "140"}, sort_keys=True),
            "tr": json.dumps({"scene_id": 42}, sort_keys=True),
        })
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=eng)

    @contextmanager
    def factory():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    return factory


class TestLookup:
    def test_hit_returns_counts(self, tmp_path):
        lk = LearnedPatternLookup(_make_db(tmp_path))
        assert lk(("techno", "drop", "140"), 42) == (18, 20)

    def test_normalizes_case_like_aggregator(self, tmp_path):
        """Aggregator lowercased genre/section — roher AudioContext
        ("Techno", "DROP") muss trotzdem matchen (B-159/B-182-Klasse)."""
        lk = LearnedPatternLookup(_make_db(tmp_path))
        assert lk(("Techno", "DROP", "140"), 42) == (18, 20)

    def test_miss_returns_neutral_zero(self, tmp_path):
        lk = LearnedPatternLookup(_make_db(tmp_path))
        assert lk(("techno", "drop", "140"), 999) == (0, 0)

    def test_string_kinds_neutral(self, tmp_path):
        lk = LearnedPatternLookup(_make_db(tmp_path))
        assert lk("genre", "techno", 3) == 0.5
        assert lk("key", "Am", "energetic") == 0.5
        assert lk("spectral", "abc", 3) == 0.5

    def test_db_error_falls_back_neutral(self):
        def boom():
            raise RuntimeError("db weg")

        lk = LearnedPatternLookup(boom)
        assert lk(("techno", "drop", "140"), 42) == (0, 0)

    def test_cache_avoids_second_query(self, tmp_path):
        factory = _make_db(tmp_path)
        calls = {"n": 0}

        @contextmanager
        def counting():
            calls["n"] += 1
            with factory() as s:
                yield s

        lk = LearnedPatternLookup(counting)
        lk(("techno", "drop", "140"), 42)
        lk(("techno", "drop", "140"), 42)
        assert calls["n"] == 1


def test_scorer_memory_term_reacts(tmp_path):
    """End-to-End im Kleinen: Scorer mit Lookup bewertet die gelernte
    Scene besser als eine ungesehene (nur w_memory differiert)."""
    from services.pacing.scorer import AudioContext, ClipFeatures, PacingScorer

    scorer = PacingScorer(pattern_lookup=LearnedPatternLookup(_make_db(tmp_path)))
    ctx = AudioContext(
        at_timestamp_sec=10.0, at_beat_idx=4, at_section_type="drop",
        at_bpm=140.0, at_energy=0.8, at_key=None, at_key_confidence=None,
        at_harmonic_tension=None, at_mood_audio="energetic",
        at_mood_video=None, at_genre="techno", at_sub_genre=None,
        at_spectral_hash=None, at_groove_template=None, at_lufs=None,
    )

    def clip(scene_id):
        return ClipFeatures(
            clip_id=1, scene_id=scene_id, role="action",
            mood_refined="energetic", style_bucket_id=1, motion_score=0.5,
        )

    _, c_learned = scorer.score(clip(42), ctx)
    _, c_unseen = scorer.score(clip(999), ctx)
    # 18/20 Accepts -> Wilson > 0.5; ungesehen 0/0 -> 0.5
    assert c_learned["memory"] > c_unseen["memory"]


def test_product_wiring_present():
    """Quelltext-Vertrag: Produkt-Scorer bekommt den LearnedPatternLookup."""
    import inspect

    import services.pacing_service as ps
    src = inspect.getsource(ps)
    assert "pattern_lookup=LearnedPatternLookup(nullpool_session)" in src
