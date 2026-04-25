"""Cycle 9: Steer-Tab Real-Test — Lern-Loop end-to-end.

Validiert dass der nach B-159 reparierte Memory-Loop tatsaechlich
Daten persistiert und beim zweiten Run beeinflusst.

Workflow:
1. Setup: in-memory DB mit Schema
2. Synthetische ClipFeatures + AudioContext erzeugen
3. PacingPipeline.select_best() laufen lassen mit DecisionRecorder
4. Verifizieren: mem_decision wurde befuellt
5. user_verdict='accept' fuer alle Decisions setzen
6. PatternAggregator.run() laufen lassen
7. Verifizieren: mem_learned_pattern wurde befuellt mit scene_id-Keys (B-159)
8. Zweiter Run mit pattern_lookup an PacingScorer reichen
9. Verifizieren: w_memory != 0.5 fuer Clips mit Pattern-Match

Ausfuehrung:
    .venv310\\Scripts\\python.exe tests/functional_steer_tab_memory_loop.py
"""
from __future__ import annotations

import sys
import json
import logging
import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)-5s] %(name)s: %(message)s")
logger = logging.getLogger("functional_test")


def setup_db():
    """Fresh tempfile SQLite mit Base + Memory-Layer Tabellen.

    Base.metadata.create_all() erzeugt audio_tracks/video_clips/scenes/etc.
    Dann manuell die mem_*-Tabellen anlegen (sind nur in Alembic, nicht in
    SQLAlchemy-Models).
    """
    import tempfile
    from pathlib import Path
    from sqlalchemy import create_engine, event, text
    from database.models import Base, Project, AudioTrack, VideoClip, Scene

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="pb_test_")
    tmp.close()
    db_path = Path(tmp.name)

    eng = create_engine(f"sqlite:///{db_path}", echo=False)

    @event.listens_for(eng, "connect")
    def _set_pragma(dbapi_conn, _rec):
        c = dbapi_conn.cursor()
        c.execute("PRAGMA foreign_keys=ON")
        c.close()

    # Phase 1: Base-Tabellen
    Base.metadata.create_all(eng)

    # Phase 2: Memory-Layer manuell (entspricht alembic 15b79edf1d76).
    with eng.begin() as conn:
        conn.execute(text("""
            CREATE TABLE mem_pacing_run (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                audio_track_id INTEGER,  -- nullable fuer Tests
                started_at DATETIME NOT NULL,
                completed_at DATETIME,
                is_dj_mix BOOLEAN,
                total_duration_sec FLOAT,
                total_cuts INTEGER NOT NULL DEFAULT 0,
                agent_version TEXT NOT NULL,
                weights_profile TEXT NOT NULL,
                user_rating INTEGER,
                user_notes TEXT,
                steer_snapshot JSON
            )
        """))
        conn.execute(text("""
            CREATE TABLE mem_decision (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                sequence_idx INTEGER NOT NULL,
                at_timestamp_sec FLOAT NOT NULL,
                at_beat_idx INTEGER,
                at_structure_segment_id INTEGER,
                at_bpm FLOAT, at_energy FLOAT,
                at_section_type TEXT, at_key TEXT,
                at_key_confidence FLOAT, at_key_modulation BOOLEAN,
                at_harmonic_tension FLOAT, at_mood_audio TEXT,
                at_genre TEXT, at_sub_genre TEXT,
                at_spectral_hash TEXT, at_groove_template TEXT,
                at_lufs FLOAT, at_enricher_version TEXT,
                scene_id INTEGER NOT NULL,
                clip_role TEXT NOT NULL,
                clip_mood_refined TEXT NOT NULL,
                clip_style_bucket_id INTEGER NOT NULL,
                clip_motion_score FLOAT,
                agent_score FLOAT NOT NULL,
                agent_rationale JSON NOT NULL,
                user_verdict TEXT, user_verdict_at DATETIME, user_rating INTEGER,
                FOREIGN KEY(run_id) REFERENCES mem_pacing_run(id) ON DELETE CASCADE
            )
        """))
        conn.execute(text("""
            CREATE TABLE mem_learned_pattern (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                pattern_type TEXT NOT NULL,
                context_fingerprint JSON,
                target_ref JSON,
                stat_accept_count INTEGER NOT NULL DEFAULT 0,
                stat_reject_count INTEGER NOT NULL DEFAULT 0,
                stat_sample_size INTEGER NOT NULL DEFAULT 0,
                confidence FLOAT NOT NULL,
                last_updated DATETIME NOT NULL
            )
        """))
        conn.execute(text("CREATE INDEX idx_mem_lp_type ON mem_learned_pattern(pattern_type)"))
    return eng


def make_clip(clip_id: int, scene_id: int, role: str = "hero",
              mood: str = "energetic", style_bucket: int = 1,
              motion: float = 0.7) -> "ClipFeatures":
    from services.pacing.scorer import ClipFeatures
    # Zufaelliger 1152-dim Embedding-Vector
    rng = np.random.RandomState(scene_id)
    emb = rng.randn(1152).astype(np.float32)
    emb /= np.linalg.norm(emb) + 1e-9
    return ClipFeatures(
        clip_id=clip_id,
        scene_id=scene_id,
        role=role,
        mood_refined=mood,
        style_bucket_id=style_bucket,
        motion_score=motion,
        embedding=emb,
    )


def make_ctx(t: float, section_type: str = "drop", bpm: float = 128.0,
             energy: float = 0.85, genre: str = "techno") -> "AudioContext":
    from services.pacing.scorer import AudioContext
    return AudioContext(
        at_timestamp_sec=t,
        at_beat_idx=int(t * bpm / 60),
        at_section_type=section_type,
        at_bpm=bpm,
        at_energy=energy,
        at_key="A min",
        at_key_confidence=0.85,
        at_harmonic_tension=0.5,
        at_mood_audio="energetic",
        at_mood_video=None,
        at_genre=genre,
        at_sub_genre=None,
        at_spectral_hash="abc12345",
        at_groove_template="four_on_floor",
        at_lufs=-12.5,
    )


def step1_run_pipeline_with_recorder(eng) -> tuple[int, list[int]]:
    """Trigger PacingPipeline + DecisionRecorder. Return (run_id, decision_ids)."""
    from services.pacing.pipeline import PacingPipeline
    from services.pacing.scorer import PacingScorer
    from services.pacing.decision_recorder import DecisionRecorder
    from sqlalchemy import text

    # mem_pacing_run row anlegen (FK target fuer mem_decision.run_id)
    with eng.connect() as conn:
        result = conn.execute(text(
            "INSERT INTO mem_pacing_run "
            "(started_at, total_cuts, agent_version, weights_profile) "
            "VALUES (:s, :c, :v, :p) RETURNING id"
        ), {"s": datetime.datetime.now(), "c": 0,
            "v": "test-1.0", "p": "default"})
        run_id = int(result.scalar())
        conn.commit()
    logger.info("Run created: id=%d", run_id)

    # Session-Factory fuer den Recorder
    def _session_factory():
        return eng.connect()

    recorder = DecisionRecorder(session_factory=_session_factory)
    scorer = PacingScorer(weights_profile="default")
    pipeline = PacingPipeline(
        scorer=scorer,
        decision_recorder=recorder,
        run_id=run_id,
    )

    # 5 Cuts mit verschiedenen Clips
    candidates_pool = [
        make_clip(clip_id=10, scene_id=100, role="hero", mood="euphoric"),
        make_clip(clip_id=11, scene_id=101, role="action", mood="energetic"),
        make_clip(clip_id=12, scene_id=102, role="hero", mood="aggressive"),
        make_clip(clip_id=13, scene_id=103, role="filler", mood="calm"),
        make_clip(clip_id=14, scene_id=104, role="hero", mood="euphoric"),
    ]

    decision_ids: list[int] = []
    predecessor = None
    for i in range(5):
        ctx = make_ctx(t=4.0 + i * 4.0, section_type="drop", bpm=128.0)
        result = pipeline.select_best(
            candidates=candidates_pool,
            ctx=ctx,
            predecessor=predecessor,
        )
        if result.chosen is None:
            logger.warning("Cut %d: pipeline returned None — rationale=%s",
                           i, result.rationale.get("error"))
            continue
        did = result.rationale.get("persisted_decision_id")
        if did is not None:
            decision_ids.append(did)
        predecessor = result.chosen
        logger.info("Cut %d: chose clip_id=%d scene_id=%d score=%.3f decision_id=%s",
                    i, result.chosen.clip_id, result.chosen.scene_id,
                    result.rationale["chosen_score"], did)

    return run_id, decision_ids


def step2_verify_mem_decision(eng, run_id: int, expected_count: int) -> dict:
    """Pruefe dass mem_decision-Zeilen geschrieben wurden."""
    from sqlalchemy import text
    with eng.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, scene_id, agent_score, at_genre, at_section_type, at_bpm "
            "FROM mem_decision WHERE run_id = :rid ORDER BY id"
        ), {"rid": run_id}).mappings().all()

    rows = [dict(r) for r in rows]
    logger.info("mem_decision rows for run %d: %d (expected %d)",
                run_id, len(rows), expected_count)
    for r in rows:
        logger.info("  decision_id=%d scene_id=%d score=%.3f genre=%s section=%s",
                    r["id"], r["scene_id"], r["agent_score"],
                    r["at_genre"], r["at_section_type"])
    return {"row_count": len(rows), "expected": expected_count, "rows": rows}


def step3_simulate_user_verdict(eng, run_id: int) -> int:
    """User markiert alle Decisions als 'accept'."""
    from sqlalchemy import text
    with eng.connect() as conn:
        result = conn.execute(text(
            "UPDATE mem_decision SET user_verdict = 'accept', "
            "user_verdict_at = :ts, user_rating = 5 "
            "WHERE run_id = :rid"
        ), {"ts": datetime.datetime.now(), "rid": run_id})
        conn.commit()

    # mem_pacing_run.user_rating = 5 (positives Run-Rating)
    with eng.connect() as conn:
        conn.execute(text(
            "UPDATE mem_pacing_run SET user_rating = 5, completed_at = :ts "
            "WHERE id = :rid"
        ), {"ts": datetime.datetime.now(), "rid": run_id})
        conn.commit()
    logger.info("User verdict 'accept' fuer run %d gesetzt", run_id)
    return result.rowcount


def step4_run_pattern_aggregator(eng) -> int:
    """Trigger PatternAggregator → mem_learned_pattern."""
    from services.pacing.pattern_aggregator import PatternAggregator
    from services.enrichment import ENRICHER_VERSION

    def _session_factory():
        return eng.connect()

    agg = PatternAggregator(
        session_factory=_session_factory,
        enricher_version=ENRICHER_VERSION,
    )
    n_upserted = agg.run()
    logger.info("PatternAggregator: %d patterns upserted", n_upserted)
    return n_upserted


def step5_verify_mem_learned_pattern(eng) -> dict:
    """Pruefe Patterns + B-159 specific: target_ref muss scene_id enthalten."""
    from sqlalchemy import text
    with eng.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, pattern_type, context_fingerprint, target_ref, "
            "stat_accept_count, stat_reject_count, stat_sample_size, confidence "
            "FROM mem_learned_pattern"
        )).mappings().all()
    rows = [dict(r) for r in rows]
    logger.info("mem_learned_pattern rows: %d", len(rows))
    for r in rows:
        fp = json.loads(r["context_fingerprint"]) if isinstance(r["context_fingerprint"], str) else r["context_fingerprint"]
        tr = json.loads(r["target_ref"]) if isinstance(r["target_ref"], str) else r["target_ref"]
        logger.info("  pattern fp=%s tr=%s accept=%d reject=%d sample=%d conf=%.3f",
                    fp, tr, r["stat_accept_count"], r["stat_reject_count"],
                    r["stat_sample_size"], r["confidence"])
    return {"row_count": len(rows), "rows": rows}


def step6_verify_b159_lookup_works(eng) -> dict:
    """Der entscheidende Test: nach Patterns gespeichert, soll der Scorer
    sie via clip.scene_id (NICHT clip.clip_id) wiederfinden.

    Wir bauen einen pattern_lookup-Adapter der die DB liest und reichen ihn
    an den Scorer. w_memory-Term sollte != 0.5 (Wilson-neutral) sein
    fuer Clips deren scene_id in mem_learned_pattern ist.
    """
    from sqlalchemy import text
    from services.pacing.scorer import (
        PacingScorer, ClipFeatures, AudioContext, historical_accept_rate,
    )

    # pattern_lookup: (fingerprint_tuple, scene_id) → (accepts, total)
    def db_lookup(fingerprint, scene_id):
        # fingerprint = (genre, section_type, bpm_str)
        genre, section, bpm_str = fingerprint
        with eng.connect() as conn:
            result = conn.execute(text(
                "SELECT stat_accept_count, stat_sample_size "
                "FROM mem_learned_pattern "
                "WHERE pattern_type = 'context_preference' "
                "  AND json_extract(context_fingerprint, '$.genre') IS :g "
                "  AND json_extract(context_fingerprint, '$.section_type') IS :s "
                "  AND json_extract(context_fingerprint, '$.bpm_bucket') IS :b "
                "  AND json_extract(target_ref, '$.scene_id') = :sid "
                "LIMIT 1"
            ), {"g": (genre or "").lower() if genre else None,
                "s": (section or "").lower() if section else None,
                "b": bpm_str, "sid": scene_id}).fetchone()
        if result is None:
            return (0, 0)
        return (int(result[0] or 0), int(result[1] or 0))

    # Test-Clip mit scene_id der in der DB als Pattern existiert
    clip_known = make_clip(clip_id=999, scene_id=100, role="hero",
                            mood="euphoric")  # scene_id=100 ist im DB
    # Test-Clip mit unbekannter scene_id
    clip_unknown = make_clip(clip_id=998, scene_id=9999, role="hero",
                              mood="euphoric")
    ctx = make_ctx(t=10.0, section_type="drop", bpm=128.0, genre="techno")

    fingerprint = (ctx.at_genre, ctx.at_section_type,
                   f"{ctx.at_bpm:.0f}" if ctx.at_bpm else None)

    rate_known = historical_accept_rate(fingerprint, clip_known, db_lookup)
    rate_unknown = historical_accept_rate(fingerprint, clip_unknown, db_lookup)
    raw_lookup_known = db_lookup(fingerprint, clip_known.scene_id)
    raw_lookup_unknown = db_lookup(fingerprint, clip_unknown.scene_id)

    logger.info("B-159 Verification:")
    logger.info("  Known scene_id=100: raw_lookup=%s → wilson=%.3f",
                raw_lookup_known, rate_known)
    logger.info("  Unknown scene_id=9999: raw_lookup=%s → wilson=%.3f",
                raw_lookup_unknown, rate_unknown)

    return {
        "rate_known": rate_known,
        "rate_unknown": rate_unknown,
        "raw_lookup_known": raw_lookup_known,
        "raw_lookup_unknown": raw_lookup_unknown,
        "b159_works": rate_known != 0.5 and raw_lookup_known[1] > 0,
    }


def main():
    logger.info("=" * 70)
    logger.info("Cycle 9 Functional Test — Lern-Loop nach B-159 Fix")
    logger.info("=" * 70)

    eng = setup_db()
    logger.info("DB initialized (in-memory)")

    # Phase 1: Pipeline-Run mit Decision-Persistence
    logger.info("\n--- Phase 1: PacingPipeline → DecisionRecorder ---")
    run_id, decision_ids = step1_run_pipeline_with_recorder(eng)
    logger.info("→ %d decisions persisted: %s", len(decision_ids), decision_ids)

    # Phase 2: Verifikation
    logger.info("\n--- Phase 2: mem_decision verify ---")
    md = step2_verify_mem_decision(eng, run_id, expected_count=5)

    # Phase 3: User-Feedback simulieren
    logger.info("\n--- Phase 3: User Verdict 'accept' ---")
    n_updated = step3_simulate_user_verdict(eng, run_id)
    logger.info("→ %d decisions marked as 'accept'", n_updated)

    # Phase 4: PatternAggregator
    logger.info("\n--- Phase 4: PatternAggregator.run() ---")
    n_patterns = step4_run_pattern_aggregator(eng)

    # Phase 5: mem_learned_pattern verify
    logger.info("\n--- Phase 5: mem_learned_pattern verify ---")
    pat = step5_verify_mem_learned_pattern(eng)

    # Phase 6: B-159 — Lookup via scene_id (NICHT clip_id)
    logger.info("\n--- Phase 6: B-159 Lookup-Verification ---")
    b159 = step6_verify_b159_lookup_works(eng)

    # ── Final Report ──
    logger.info("\n" + "=" * 70)
    logger.info("FINAL REPORT")
    logger.info("=" * 70)
    logger.info("mem_decision: %d/%d rows", md["row_count"], md["expected"])
    logger.info("mem_learned_pattern: %d rows", pat["row_count"])
    logger.info("B-159 (scene_id lookup): %s",
                "WORKS ✓" if b159["b159_works"] else "BROKEN ✗")
    logger.info("  - rate_known=%.3f (raw=%s)",
                b159["rate_known"], b159["raw_lookup_known"])
    logger.info("  - rate_unknown=%.3f (raw=%s)",
                b159["rate_unknown"], b159["raw_lookup_unknown"])

    # Exit-Code: 0 wenn alles OK, 1 wenn was schief lief
    all_ok = (
        md["row_count"] == md["expected"]
        and pat["row_count"] > 0
        and b159["b159_works"]
    )
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
