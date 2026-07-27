"""Credit-Assignment fuer Brain-V3-Feedback (2026-07-27).

BEFUND vorher: services/brain/feedback_logger.py schrieb bei JEDEM Klick
denselben alpha/beta-Delta in ALLE 17 Achsen x 6 Kontext-Level. Belegt in
der echten %APPDATA%\\PB_Studio\\brain_v3\\weights.db: alle 17 Achsen auf
Level 0 standen auf identischen Werten (178/249). services/brain/scorer.py
bildet einen GEWICHTETEN Mittelwert — bei identischen Gewichten ist das ein
arithmetisches Mittel, die Kandidaten-Reihenfolge kann sich dadurch nicht
aendern. Jeder Klick verpuffte.

Diese Datei ist die Beweispflicht:
  * uniform  -> Achsen bleiben identisch, Reihenfolge bleibt
  * weighted -> Achsen bekommen UNTERSCHIEDLICHE Werte und die
                Kandidaten-Reihenfolge kippt tatsaechlich
"""
from __future__ import annotations

import sqlite3
import statistics
from pathlib import Path

import pytest

from services.brain.bridge_dimensions import BridgeDimensions, ClipCandidate
from services.brain.cold_start import BRIDGE_AXES
from services.brain.context_resolver import CutContext, context_keys
from services.brain.feedback_logger import (
    FeedbackLogger,
    PACING_TERM_TO_AXES,
    axis_contributions_from_rationale,
    credit_weights,
)
from services.brain.scorer import Scorer
from services.brain.storage.migration_runner import migrate
from services.brain.weight_store import WeightStore

_MIGRATIONS = (
    Path(__file__).resolve().parents[2]
    / "services" / "brain" / "storage" / "sql_migrations" / "weights"
)


@pytest.fixture
def weights_db(tmp_path: Path) -> Path:
    db = tmp_path / "weights.db"
    migrate(db, _MIGRATIONS)
    return db


@pytest.fixture
def store(weights_db: Path) -> WeightStore:
    ws = WeightStore(weights_db)
    yield ws
    ws.close()


# ---------------------------------------------------------------------------
# Szenario: zwei Kandidaten, die sich NUR in motion/brightness unterscheiden.
# Beide Achsen starten auf demselben Cold-Start-Default (0.5), damit der
# Test wirklich das Feedback misst und nicht die Default-Heterogenitaet.
# ---------------------------------------------------------------------------
CTX = CutContext(
    raw_audio_features={"energy": 0.9, "spectral_centroid_norm": 0.9},
)

# A: perfekte Motion-Passung, schlechte Brightness-Passung -> initial vorn
CAND_A = ClipCandidate(clip_id="A", duration_s=3.0, motion_score=0.9, brightness=0.15)
# B: schlechte Motion-Passung, perfekte Brightness-Passung
CAND_B = ClipCandidate(clip_id="B", duration_s=3.0, motion_score=0.1, brightness=0.9)


def _order(store: WeightStore) -> list[str]:
    scorer = Scorer(BridgeDimensions(), store)
    return [s.candidate.clip_id for s in scorer.score_all([CAND_A, CAND_B], CTX)]


def _level0_values(db: Path) -> dict[str, tuple[float, float]]:
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            "SELECT axis, positive_count, negative_count FROM axis_weights "
            "WHERE context_level = 0"
        ).fetchall()
    finally:
        conn.close()
    return {r[0]: (float(r[1]), float(r[2])) for r in rows}


# ---------------------------------------------------------------------------
# 1. Regression: der alte Uniform-Pfad
# ---------------------------------------------------------------------------
def test_uniform_feedback_leaves_all_axes_identical(store: WeightStore, weights_db: Path):
    """Ohne axis_contributions bleibt alles beim Alten — genau der Befund."""
    fl = FeedbackLogger(store)
    keys = context_keys(CTX)
    for _ in range(5):
        diag = fl.log_feedback("perfect", keys)
    assert diag["credit_mode"] == "uniform"

    values = _level0_values(weights_db)
    assert len(values) == 17
    assert len(set(values.values())) == 1, (
        f"Uniform-Pfad muss alle 17 Achsen identisch lassen: {values}"
    )


def test_uniform_feedback_cannot_change_candidate_order(store: WeightStore):
    """Beweis der Wirkungslosigkeit: identische Gewichte -> gleiche Ordnung."""
    before = _order(store)
    assert before == ["A", "B"]

    fl = FeedbackLogger(store)
    keys = context_keys(CTX)
    for _ in range(10):
        fl.log_feedback("perfect", keys)

    assert _order(store) == before, (
        "Uniform-Feedback darf (und kann) die Reihenfolge dieser beiden "
        "Kandidaten nicht aendern — das war der Kern des Bugs."
    )


# ---------------------------------------------------------------------------
# 2. Credit-Assignment: Varianz + Reihenfolge
# ---------------------------------------------------------------------------
def test_weighted_feedback_produces_axis_variance(store: WeightStore, weights_db: Path):
    fl = FeedbackLogger(store)
    keys = context_keys(CTX)
    contributions = {
        "brightness_match_weight": 1.0,
        "motion_match_weight": 0.05,
        "pace_match_weight": 0.4,
    }
    for _ in range(5):
        diag = fl.log_feedback("perfect", keys, axis_contributions=contributions)

    assert diag["credit_mode"] == "weighted"
    assert diag["n_axes_credited"] == 3

    values = _level0_values(weights_db)
    # Achsen ohne Beitrag existieren gar nicht -> sie lernen nicht mit.
    assert set(values) == set(contributions)
    alphas = [a for a, _b in values.values()]
    assert len(set(alphas)) == 3, f"Achsen muessen sich unterscheiden: {values}"
    assert statistics.pvariance(alphas) > 0.0
    # dominante Achse behaelt den vollen Plan-Doc-Delta (5 x 2.0)
    assert values["brightness_match_weight"][0] == pytest.approx(10.0)
    assert values["motion_match_weight"][0] == pytest.approx(0.5)


def test_weighted_feedback_changes_candidate_order(store: WeightStore):
    """DER Beweis: nach gewichtetem Feedback kippt die Reihenfolge."""
    assert _order(store) == ["A", "B"]

    fl = FeedbackLogger(store)
    keys = context_keys(CTX)
    # Der User lobt einen Cut, bei dem die Brightness-Passung den Ausschlag
    # gab; Motion trug fast nichts bei.
    contributions = {"brightness_match_weight": 1.0, "motion_match_weight": 0.05}
    for _ in range(5):
        fl.log_feedback("perfect", keys, axis_contributions=contributions)

    after = _order(store)
    assert after == ["B", "A"], (
        f"Reihenfolge haette kippen muessen, ist aber {after}"
    )


def test_axis_without_contribution_is_not_written(store: WeightStore, weights_db: Path):
    fl = FeedbackLogger(store)
    fl.log_feedback(
        "no_match",
        context_keys(CTX),
        axis_contributions={"kick_weight": 1.0, "snare_weight": 0.0},
    )
    values = _level0_values(weights_db)
    assert set(values) == {"kick_weight"}
    assert values["kick_weight"] == (0.0, 2.0)


def test_negative_rating_punishes_the_responsible_axis(store: WeightStore, weights_db: Path):
    fl = FeedbackLogger(store)
    fl.log_feedback(
        "no_match",
        context_keys(CTX),
        axis_contributions={"mood_match_weight": 1.0, "genre": 5.0},  # genre = keine Achse
    )
    values = _level0_values(weights_db)
    assert set(values) == {"mood_match_weight"}
    assert values["mood_match_weight"] == (0.0, 2.0)


# ---------------------------------------------------------------------------
# 3. credit_weights / Rationale-Extraktion
# ---------------------------------------------------------------------------
def test_credit_weights_normalises_to_max():
    credits = credit_weights({"kick_weight": 2.0, "snare_weight": 1.0})
    assert credits == pytest.approx({"kick_weight": 1.0, "snare_weight": 0.5})


def test_credit_weights_uses_magnitude_not_sign():
    """Ein starker Penalty hat die Entscheidung genauso gepraegt."""
    credits = credit_weights({"scene_cut_weight": -2.0, "kick_weight": 1.0})
    assert credits["scene_cut_weight"] == pytest.approx(1.0)


def test_credit_weights_ignores_unknown_axes_and_nonfinite():
    assert credit_weights({"nicht_existent": 1.0}) == {}
    assert credit_weights({"kick_weight": float("nan")}) == {}
    assert credit_weights({}) == {}
    assert credit_weights(None) == {}


def test_rationale_prefers_brain_v3_scores():
    rationale = {
        "brain_v3_scores": {"kick_weight": 0.8, "snare_weight": 0.2},
        "contribs": {"energy": 5.0},
    }
    assert axis_contributions_from_rationale(rationale) == {
        "kick_weight": 0.8, "snare_weight": 0.2,
    }


def test_rationale_falls_back_to_mapped_pacing_contribs():
    contributions = axis_contributions_from_rationale(
        {"contribs": {"energy": 0.9, "spectral": 0.3, "memory": 99.0}}
    )
    # energy verteilt sich auf 3 Achsen, spectral auf 1, memory ist bewusst
    # nicht gemappt (kein Bridge-Analogon).
    assert set(contributions) == {
        "energy_weight", "energy_threshold", "motion_match_weight",
        "brightness_match_weight",
    }
    assert contributions["energy_weight"] == pytest.approx(0.3)
    assert contributions["brightness_match_weight"] == pytest.approx(0.3)


def test_rationale_without_signal_is_empty():
    assert axis_contributions_from_rationale(None) == {}
    assert axis_contributions_from_rationale({}) == {}
    assert axis_contributions_from_rationale({"contribs": {}}) == {}


def test_pacing_term_map_targets_are_real_axes():
    for term, axes in PACING_TERM_TO_AXES.items():
        for axis in axes:
            assert axis in BRIDGE_AXES, f"{term} -> {axis} ist keine Bridge-Achse"


# ---------------------------------------------------------------------------
# 4. WeightStore.update_many ist der einzige Schreibpfad
# ---------------------------------------------------------------------------
def test_update_many_is_atomic(store: WeightStore, weights_db: Path):
    store.update_many([
        ("kick_weight", 0, "", 1.0, 0.0),
        ("snare_weight", 0, "", 0.0, 3.0),
    ])
    values = _level0_values(weights_db)
    assert values == {"kick_weight": (1.0, 0.0), "snare_weight": (0.0, 3.0)}


def test_update_many_skips_zero_deltas(store: WeightStore, weights_db: Path):
    assert store.update_many([("kick_weight", 0, "", 0.0, 0.0)]) == 0
    assert _level0_values(weights_db) == {}


def test_update_many_rejects_unknown_axis(store: WeightStore):
    with pytest.raises(ValueError):
        store.update_many([("nicht_existent", 0, "", 1.0, 0.0)])


def test_update_delegates_to_update_many(store: WeightStore, weights_db: Path):
    store.update("kick_weight", 2, "section=drop|mood=dark|", 1.5, 0.5)
    ab = store.get_alpha_beta("kick_weight", 2, "section=drop|mood=dark|")
    assert (ab.alpha, ab.beta) == (1.5, 0.5)


# ---------------------------------------------------------------------------
# 5. FeedbackService: echter CutContext + echte Beitraege aus mem_decision
# ---------------------------------------------------------------------------
def _full_schema_db(tmp_path: Path, rationale: str):
    """mem_decision mit allen Spalten, die das Lern-Signal braucht."""
    from contextlib import contextmanager

    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    eng = create_engine(f"sqlite:///{(tmp_path / 'full.db').as_posix()}")
    with eng.begin() as c:
        c.execute(text("""
            CREATE TABLE mem_decision (
                id INTEGER PRIMARY KEY,
                run_id INTEGER, scene_id INTEGER, sequence_idx INTEGER,
                at_section_type TEXT, at_timestamp_sec REAL,
                at_energy REAL, at_mood_audio TEXT, at_bpm REAL,
                clip_motion_score REAL, agent_rationale TEXT,
                user_verdict TEXT, user_verdict_at TEXT, user_rating INTEGER
            )
        """))
        c.execute(text("""
            CREATE TABLE mem_user_feedback_event (
                id INTEGER PRIMARY KEY,
                decision_id INTEGER, run_id INTEGER,
                event_type TEXT, payload TEXT, created_at TEXT
            )
        """))
        c.execute(
            text("""
            INSERT INTO mem_decision
            (run_id, scene_id, sequence_idx, at_section_type, at_timestamp_sec,
             at_energy, at_mood_audio, at_bpm, clip_motion_score, agent_rationale)
            VALUES (7, 42, 3, 'buildup', 12.5, 0.92, 'dramatic', 145.0, 0.9, :r)
        """),
            {"r": rationale},
        )
    Session = sessionmaker(bind=eng)

    @contextmanager
    def factory():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    return factory


def test_feedback_service_delivers_real_context_and_contributions(tmp_path, monkeypatch):
    import json

    import services.brain.feedback_logger as fl
    from services.feedback_service import FeedbackService

    rationale = json.dumps({
        "brain_v3_scores": {"kick_weight": 0.8, "mood_match_weight": 0.1},
        "contribs": {"energy": 1.0},
    })
    seen: dict = {}

    def _fake_submit(rating, context=None, axis_contributions=None, weight_store=None):
        seen["rating"] = rating
        seen["context"] = context
        seen["axis_contributions"] = axis_contributions
        return {"n_buckets_updated": 12, "credit_mode": "weighted", "n_axes_credited": 2}

    monkeypatch.setattr(fl, "submit_feedback", _fake_submit)

    svc = FeedbackService(session_factory=_full_schema_db(tmp_path, rationale))
    assert svc.record_verdict(7, 42, "accept").success

    ctx = seen["context"]
    # 'buildup' -> 'build' (context_mapping), dramatic -> dark,
    # energy 0.92 -> high, motion 0.9 -> extreme, bpm 145 -> fast
    assert ctx.audio_section_type == "build"
    assert ctx.audio_mood == "dark"
    assert ctx.audio_energy_level == "high"
    assert ctx.video_motion_class == "extreme"
    assert ctx.video_pace_class == "fast"
    # Level-5-Key ist damit NICHT mehr der neutrale Default -> Backoff greift
    assert context_keys(ctx)[5] != context_keys(CutContext())[5]
    # Beitraege kommen aus brain_v3_scores, nicht aus contribs
    assert seen["axis_contributions"] == {
        "kick_weight": 0.8, "mood_match_weight": 0.1,
    }
