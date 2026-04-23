"""T7.4: End-to-end memory-learning loop.

Run pacing → capture score → user accepts the chosen clip → pattern is aggregated →
run pacing a second time with memory-aware scoring → the accepted clip scores HIGHER
than it did the first time.

This is the definitive "the loop closes" test for P7.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from services.pacing.decision_recorder import DecisionRecorder
from services.pacing.pattern_aggregator import (
    PatternAggregator,
    bpm_bucket,
    make_context_fingerprint,
)
from services.pacing.pipeline import PacingPipeline
from services.pacing.scorer import AudioContext, ClipFeatures, PacingScorer
from services.stats.wilson_lower_bound import wilson_lower_bound

# ---------------------------------------------------------------------------
# DB bootstrap helpers
# ---------------------------------------------------------------------------


_LAST_GOOD_REVISION = "a3df65cc10b1"

# Studio-Brain tables — created by Alembic migrations, NOT by create_all().
_STUDIO_BRAIN_TABLES = frozenset(
    {
        "struct_clip_tags",
        "struct_style_bucket",
        "struct_compat_edge",
        "mem_pacing_run",
        "mem_decision",
        "mem_learned_pattern",
        "mem_user_feedback_event",
    }
)


def _build_sqlite(tmp_path: Path) -> tuple[Any, Any]:
    """Create a fresh SQLite DB with:
      1. Baseline schema via Base.metadata.create_all() (excludes studio-brain tables).
      2. Alembic stamp at pre-studio-brain revision.
      3. Alembic upgrade to head (adds mem_* tables).
    Returns (engine, Session).
    """
    from alembic import command
    from alembic.config import Config

    from database.models import Base

    db_path = tmp_path / "mem.db"
    ini_path = Path(__file__).parent.parent.parent / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")

    # Step 1: create all baseline tables (not the studio-brain ones)
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    tables_to_create = [
        t for t in Base.metadata.sorted_tables if t.name not in _STUDIO_BRAIN_TABLES
    ]
    Base.metadata.create_all(engine, tables=tables_to_create)
    engine.dispose()

    # Step 2: stamp so Alembic knows where we are
    command.stamp(cfg, _LAST_GOOD_REVISION)

    # Step 3: upgrade to head to create mem_* tables
    command.upgrade(cfg, "head")

    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Session = sessionmaker(bind=engine)
    return engine, Session


def _seed_baseline(engine: Any) -> None:
    """Insert the minimum required rows: project, audio_track, video_clip, scenes."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO projects (id, name, path, resolution, fps) "
                "VALUES (1, 'test_proj', '/tmp/proj', '1920x1080', 30.0)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO audio_tracks (id, project_id, file_path, duration, bpm) "
                "VALUES (1, 1, '/f.mp3', 120.0, 140.0)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO video_clips (id, project_id, file_path, duration, playback_offset) "
                "VALUES (1, 1, '/clip.mp4', 60.0, 0.0)"
            )
        )
        # Scenes for scene_id 10 (clip_id=1 → scene_id=10) and scene_id 20 (clip_id=2)
        for scene_id in (10, 20):
            conn.execute(
                text(
                    "INSERT INTO scenes (id, video_clip_id, start_time, end_time) "
                    "VALUES (:sid, 1, :st, :en)"
                ),
                {"sid": scene_id, "st": (scene_id - 10) * 5.0, "en": scene_id * 5.0},
            )


def _seed_run(engine: Any) -> int:
    """Insert a mem_pacing_run row on audio_track 1; return its id."""
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "INSERT INTO mem_pacing_run "
                "(audio_track_id, started_at, is_dj_mix, total_duration_sec, "
                "total_cuts, agent_version, weights_profile) VALUES "
                "(1, datetime('now'), 0, 120.0, 0, 'test', 'default') RETURNING id"
            )
        ).fetchone()
        assert row is not None
        return int(row[0])


def _seed_run_2(engine: Any) -> int:
    """Insert a second mem_pacing_run; return its id."""
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "INSERT INTO mem_pacing_run "
                "(audio_track_id, started_at, is_dj_mix, total_duration_sec, "
                "total_cuts, agent_version, weights_profile) VALUES "
                "(1, datetime('now'), 0, 120.0, 0, 'test-v1', 'default') RETURNING id"
            )
        ).fetchone()
        assert row is not None
        return int(row[0])


# ---------------------------------------------------------------------------
# Context / clip builders
# ---------------------------------------------------------------------------


def _drop_context(ts: float = 60.0) -> AudioContext:
    return AudioContext(
        at_timestamp_sec=ts,
        at_beat_idx=120,
        at_section_type="drop",
        at_bpm=140.0,
        at_energy=0.8,
        at_key="Am",
        at_key_confidence=0.9,
        at_harmonic_tension=0.75,
        at_mood_audio="energetic",
        at_mood_video="energetic",
        at_genre="psytrance",
        at_sub_genre="dark_psy",
        at_spectral_hash="h",
        at_groove_template="fotf",
        at_lufs=-8.5,
    )


def _make_clip(
    clip_id: int,
    role: str = "hero",
    mood: str = "euphoric",
    style_bucket_id: int = 1,
    motion: float = 0.6,
    embedding: np.ndarray | None = None,
) -> ClipFeatures:
    if embedding is None:
        rng = np.random.default_rng(clip_id)
        embedding = rng.standard_normal(8).astype(np.float32)
    return ClipFeatures(
        clip_id=clip_id,
        scene_id=clip_id * 10,
        role=role,
        mood_refined=mood,
        style_bucket_id=style_bucket_id,
        motion_score=motion,
        embedding=embedding,
    )


# ---------------------------------------------------------------------------
# pattern_lookup factory
# ---------------------------------------------------------------------------

# The scorer calls:
#   historical_accept_rate → pattern_lookup(fingerprint_tuple, clip_id) → (accepts, total)
#   genre_prior            → pattern_lookup("genre", audio_genre, style_bucket_id) → float
#   key_prior              → pattern_lookup("key", audio_key, clip_mood) → float
#   spectral_fit           → pattern_lookup("spectral", spectral_hash, style_bucket_id) → float
#
# So the first argument is either a tuple (memory lookup) or a string (other lookups).
# We dispatch on isinstance(first_arg, tuple).


def _make_pattern_lookup(Session: Any) -> Callable[..., Any]:
    """Build a pattern_lookup callable that the PacingScorer accepts.

    Memory branch: first arg is the fingerprint tuple (at_genre, at_section_type, bpm_str);
                   second arg is clip_id. Returns (accepts, total).
    Other branches: first arg is a string kind; return 0.5 (Wilson-neutral).
    """

    def lookup(*args: Any) -> Any:
        first = args[0]
        if isinstance(first, tuple):
            # Memory lookup: (fingerprint_tuple, clip_id)
            fp_tuple: tuple[str | None, ...] = first
            clip_id: int = int(args[1])
            genre = fp_tuple[0]
            section_type = fp_tuple[1]
            bpm_str = fp_tuple[2]
            # PatternAggregator stores target_ref as {"scene_id": scene_id}
            # ClipFeatures.scene_id == clip_id * 10
            scene_id = clip_id * 10
            session = Session()
            try:
                row = (
                    session.execute(
                        text("""
                        SELECT stat_accept_count, stat_sample_size
                        FROM mem_learned_pattern
                        WHERE pattern_type = 'context_preference'
                          AND json_extract(context_fingerprint, '$.genre')
                              IS :genre
                          AND json_extract(context_fingerprint, '$.section_type')
                              IS :section_type
                          AND json_extract(context_fingerprint, '$.bpm_bucket')
                              IS :bpm_bucket
                          AND json_extract(target_ref, '$.scene_id') = :scene_id
                        LIMIT 1
                    """),
                        {
                            "genre": genre,
                            "section_type": section_type,
                            "bpm_bucket": bpm_str,
                            "scene_id": scene_id,
                        },
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    return (0, 0)
                return (int(row["stat_accept_count"]), int(row["stat_sample_size"]))
            finally:
                session.close()
        # Other kinds ("genre", "key", "spectral"): return neutral
        return 0.5

    return lookup


# ---------------------------------------------------------------------------
# Helpers: seed synthetic accepts without going through the pipeline
# ---------------------------------------------------------------------------


def _seed_extra_accepts(
    engine: Any,
    run_id: int,
    scene_id: int,
    ctx: AudioContext,
    n: int,
) -> None:
    """Insert n synthetic mem_decision rows already marked user_verdict='accept'.

    These rows bypass the pipeline so they feed PatternAggregator with extra
    signal. They reuse the same scene_id / fingerprint as the real decision.
    The at_enricher_version must match services.enrichment.ENRICHER_VERSION.
    """
    from services.enrichment import ENRICHER_VERSION

    with engine.begin() as conn:
        for i in range(n):
            conn.execute(
                text(
                    "INSERT INTO mem_decision "
                    "(run_id, sequence_idx, at_timestamp_sec, at_beat_idx, "
                    "at_bpm, at_energy, at_section_type, at_key, at_key_confidence, "
                    "at_harmonic_tension, at_mood_audio, at_genre, at_sub_genre, "
                    "at_spectral_hash, at_groove_template, at_lufs, at_enricher_version, "
                    "scene_id, clip_role, clip_mood_refined, clip_style_bucket_id, "
                    "clip_motion_score, agent_score, agent_rationale, user_verdict) "
                    "VALUES "
                    "(:run_id, :seq, :ts, :beat, :bpm, :energy, :section_type, "
                    ":key, :key_conf, :tension, :mood_audio, :genre, :sub_genre, "
                    ":spectral, :groove, :lufs, :enricher, "
                    ":scene_id, :role, :mood, :bucket, :motion, :score, :rationale, 'accept')"
                ),
                {
                    "run_id": run_id,
                    "seq": 1000 + i,  # avoid sequence_idx collision
                    "ts": ctx.at_timestamp_sec,
                    "beat": ctx.at_beat_idx,
                    "bpm": ctx.at_bpm,
                    "energy": ctx.at_energy,
                    "section_type": ctx.at_section_type,
                    "key": ctx.at_key,
                    "key_conf": ctx.at_key_confidence,
                    "tension": ctx.at_harmonic_tension,
                    "mood_audio": ctx.at_mood_audio,
                    "genre": ctx.at_genre,
                    "sub_genre": ctx.at_sub_genre,
                    "spectral": ctx.at_spectral_hash,
                    "groove": ctx.at_groove_template,
                    "lufs": ctx.at_lufs,
                    "enricher": ENRICHER_VERSION,
                    "scene_id": scene_id,
                    "role": "hero",
                    "mood": "euphoric",
                    "bucket": 1,
                    "motion": 0.6,
                    "score": 0.8,
                    "rationale": json.dumps({"synthetic": True}),
                },
            )


# ---------------------------------------------------------------------------
# Test 1: main loop-closes assertion
# ---------------------------------------------------------------------------


def test_memory_loop_closes_same_clip_scores_higher_in_second_run(
    tmp_path: Path,
) -> None:
    """End-to-end: positive feedback on a chosen clip in run 1 must increase
    that clip's w_memory contribution in run 2, so its total score goes up.

    The pitfall noted in the spec (Wilson(1,1)≈0.207 < 0.5 neutral) means
    a SINGLE accept would LOWER the memory contrib. We therefore seed 9
    additional synthetic accepts so PatternAggregator sees 10 accepts total
    → Wilson(10,10)≈0.722 which beats the neutral 0.5 clearly.
    """
    engine, Session = _build_sqlite(tmp_path)
    _seed_baseline(engine)
    run_id_1 = _seed_run(engine)

    # ── Run 1: no pattern_lookup → memory term is 0.5-neutral ────────────────
    candidates = [
        _make_clip(clip_id=1, role="hero"),
        _make_clip(clip_id=2, role="hero"),
    ]
    ctx = _drop_context()

    scorer_without_memory = PacingScorer(weights_profile="default")
    recorder = DecisionRecorder(session_factory=Session)
    pipe1 = PacingPipeline(
        scorer=scorer_without_memory,
        decision_recorder=recorder,
        run_id=run_id_1,
    )
    res1 = pipe1.select_best(candidates, ctx)
    assert res1.chosen is not None
    chosen_clip_1 = res1.chosen
    score_run1 = res1.rationale["chosen_score"]

    # Verify run 1 memory contrib is neutral 0.5 × w_memory=0.20 = 0.10
    run1_memory_contrib: float | None = None
    clip_1_score_run1: float | None = None
    for sr in res1.rationale["stage_results"]:
        if sr["clip_id"] == chosen_clip_1.clip_id:
            run1_memory_contrib = sr["contribs"]["memory"]
            clip_1_score_run1 = sr["soft_score"]
            break
    assert run1_memory_contrib is not None
    assert clip_1_score_run1 is not None
    assert (
        abs(run1_memory_contrib - 0.5 * 0.20) < 1e-6
    ), f"Expected neutral memory contrib 0.10, got {run1_memory_contrib}"

    # ── User accepts the chosen clip ─────────────────────────────────────────
    decision_id = res1.rationale.get("persisted_decision_id")
    assert decision_id is not None, "Bug F regression: pipeline didn't persist decision"
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO mem_user_feedback_event "
                "(decision_id, run_id, event_type, created_at) "
                "VALUES (:did, :rid, 'accept', datetime('now'))"
            ),
            {"did": decision_id, "rid": run_id_1},
        )
        conn.execute(
            text("UPDATE mem_decision SET user_verdict = 'accept' WHERE id = :id"),
            {"id": decision_id},
        )

    # Seed 9 extra synthetic accepts → total 10 accepts for this (scene, fingerprint)
    # Wilson(10, 10) ≈ 0.722 > 0.5; this guarantees the memory contrib rises.
    _seed_extra_accepts(
        engine=engine,
        run_id=run_id_1,
        scene_id=chosen_clip_1.scene_id,
        ctx=ctx,
        n=9,
    )

    # ── Aggregate patterns ────────────────────────────────────────────────────
    agg = PatternAggregator(session_factory=Session)
    n_patterns = agg.run()
    assert n_patterns >= 1

    # Verify the pattern row contains exactly 10 accepts
    with engine.begin() as conn:
        pat = (
            conn.execute(
                text(
                    "SELECT stat_accept_count, stat_sample_size, confidence "
                    "FROM mem_learned_pattern "
                    "WHERE json_extract(target_ref, '$.scene_id') = :sid",
                ),
                {"sid": chosen_clip_1.scene_id},
            )
            .mappings()
            .one()
        )
    assert (
        pat["stat_accept_count"] == 10
    ), f"Expected 10 accepts, got {pat['stat_accept_count']}"
    assert pat["stat_sample_size"] == 10
    observed_wilson = float(pat["confidence"])
    # Wilson(10,10) ≈ 0.722
    assert observed_wilson > 0.5, f"Wilson(10,10) should be >0.5, got {observed_wilson}"

    # ── Run 2: same candidates + ctx, but with memory-aware scorer ───────────
    run_id_2 = _seed_run_2(engine)
    pattern_lookup = _make_pattern_lookup(Session)
    scorer_with_memory = PacingScorer(
        weights_profile="default", pattern_lookup=pattern_lookup
    )
    pipe2 = PacingPipeline(
        scorer=scorer_with_memory,
        decision_recorder=DecisionRecorder(session_factory=Session),
        run_id=run_id_2,
    )
    res2 = pipe2.select_best(candidates, ctx)
    assert res2.chosen is not None

    # Extract scores for chosen_clip_1 from run 2
    clip_1_score_run2: float | None = None
    clip_1_memory_contrib_run2: float | None = None
    for sr in res2.rationale["stage_results"]:
        if sr["clip_id"] == chosen_clip_1.clip_id:
            clip_1_score_run2 = sr["soft_score"]
            clip_1_memory_contrib_run2 = sr["contribs"]["memory"]
            break
    assert clip_1_score_run2 is not None
    assert clip_1_memory_contrib_run2 is not None

    # ── Core assertions: memory-aware scoring boosted the accepted clip ───────
    assert clip_1_memory_contrib_run2 > run1_memory_contrib, (
        f"w_memory contribution did not grow: "
        f"run1={run1_memory_contrib:.6f} → run2={clip_1_memory_contrib_run2:.6f}"
    )
    assert clip_1_score_run2 > clip_1_score_run1, (
        f"Total score did not rise for the accepted clip: "
        f"run1={clip_1_score_run1:.6f} → run2={clip_1_score_run2:.6f}"
    )

    # Report Wilson values for tuning reference
    # Wilson(1,1) ≈ 0.207, Wilson(10,10) ≈ 0.722
    expected_wilson_10 = wilson_lower_bound(10, 10)
    assert (
        abs(observed_wilson - expected_wilson_10) < 1e-9
    ), f"Confidence mismatch: stored={observed_wilson} vs computed={expected_wilson_10}"


# ---------------------------------------------------------------------------
# Test 2: non-feedbacked clip stays neutral
# ---------------------------------------------------------------------------


def test_memory_loop_clip_with_no_feedback_unchanged(tmp_path: Path) -> None:
    """Regression: a clip that got NO feedback should have its w_memory
    contribution unchanged between runs (Wilson 0/0 = 0.5 → 0.10)."""
    engine, Session = _build_sqlite(tmp_path)
    _seed_baseline(engine)
    run_id_1 = _seed_run(engine)

    candidates = [_make_clip(clip_id=1), _make_clip(clip_id=2)]
    ctx = _drop_context()

    scorer_run1 = PacingScorer(weights_profile="default")
    recorder = DecisionRecorder(session_factory=Session)
    pipe1 = PacingPipeline(
        scorer=scorer_run1, decision_recorder=recorder, run_id=run_id_1
    )
    res1 = pipe1.select_best(candidates, ctx)
    assert res1.chosen is not None

    chosen_id = res1.chosen.clip_id
    non_chosen_id = 2 if chosen_id == 1 else 1

    # Accept ONLY the chosen clip (+ 9 synthetics), leaving the other untouched
    decision_id = res1.rationale.get("persisted_decision_id")
    assert decision_id is not None
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE mem_decision SET user_verdict = 'accept' WHERE id = :id"),
            {"id": decision_id},
        )
    _seed_extra_accepts(
        engine=engine,
        run_id=run_id_1,
        scene_id=res1.chosen.scene_id,
        ctx=ctx,
        n=9,
    )

    PatternAggregator(session_factory=Session).run()

    # Run 2: check the NON-chosen clip's memory contrib is still neutral
    run_id_2 = _seed_run_2(engine)
    scorer_run2 = PacingScorer(
        weights_profile="default",
        pattern_lookup=_make_pattern_lookup(Session),
    )
    pipe2 = PacingPipeline(
        scorer=scorer_run2,
        decision_recorder=DecisionRecorder(session_factory=Session),
        run_id=run_id_2,
    )
    res2 = pipe2.select_best(candidates, ctx)
    assert res2.chosen is not None

    non_chosen_contrib_run2: float | None = None
    for sr in res2.rationale["stage_results"]:
        if sr["clip_id"] == non_chosen_id:
            non_chosen_contrib_run2 = sr["contribs"]["memory"]
            break
    assert (
        non_chosen_contrib_run2 is not None
    ), f"clip_id={non_chosen_id} not found in stage_results"
    # Wilson(0,0) = 0.5 → contrib = 0.5 × 0.20 = 0.10
    assert abs(non_chosen_contrib_run2 - 0.10) < 1e-6, (
        f"Non-feedbacked clip's memory contrib should be neutral 0.10, "
        f"got {non_chosen_contrib_run2}"
    )
