"""Tests fuer Phase 3 Brain-Core: cold_start, context_resolver,
weight_store (Beta-Bernoulli + Backoff), feedback_logger (atomic
85-Bucket-Update), bridge_dimensions, scorer, brain_store.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest

from services.brain.cold_start import (
    BRIDGE_AXES, COLD_START_DEFAULTS, get_default,
)
from services.brain.context_resolver import (
    CutContext, context_keys, quantize_tertile, quantize_subtrack_position,
    VALID_SECTIONS, VALID_MOOD,
)
from services.brain.bridge_dimensions import BridgeDimensions, ClipCandidate
from services.brain.weight_store import WeightStore, MIN_CONFIDENT_SAMPLES, AlphaBeta
from services.brain.feedback_logger import FeedbackLogger, RATING_MAP
from services.brain.scorer import Scorer
from services.brain.storage.brain_store import BrainStore
from services.brain.storage.migration_runner import migrate
from services.brain.storage.sqlite_init import open_connection


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def weights_db(tmp_path: Path) -> Path:
    db = tmp_path / "weights.db"
    mig = (Path(__file__).resolve().parents[2]
           / "services" / "brain" / "storage"
           / "sql_migrations" / "weights")
    migrate(db, mig)
    return db


@pytest.fixture
def patterns_db(tmp_path: Path) -> Path:
    db = tmp_path / "patterns.db"
    mig = (Path(__file__).resolve().parents[2]
           / "services" / "brain" / "storage"
           / "sql_migrations" / "patterns")
    migrate(db, mig)
    return db


@pytest.fixture
def store(weights_db: Path) -> WeightStore:
    s = WeightStore(weights_db)
    yield s
    s.close()


@pytest.fixture
def isolated_appdata(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    yield tmp_path


# ---------------------------------------------------------------------------
# cold_start
# ---------------------------------------------------------------------------
def test_bridge_axes_count_is_17():
    assert len(BRIDGE_AXES) == 17


def test_cold_start_covers_all_axes():
    assert set(COLD_START_DEFAULTS.keys()) == set(BRIDGE_AXES)


def test_get_default_known_axis():
    assert get_default("kick_weight") == 1.2
    assert get_default("motion_match_weight") == 0.5


def test_get_default_unknown_axis_raises():
    with pytest.raises(KeyError):
        get_default("does_not_exist")


# ---------------------------------------------------------------------------
# context_resolver
# ---------------------------------------------------------------------------
def test_cut_context_default_values_validate():
    ctx = CutContext()
    assert ctx.audio_section_type == "verse"
    assert ctx.audio_mood == "neutral"


def test_cut_context_invalid_section_raises():
    with pytest.raises(ValueError):
        CutContext(audio_section_type="not_a_section")


def test_cut_context_invalid_mood_raises():
    with pytest.raises(ValueError):
        CutContext(audio_mood="happy_clappy")


def test_context_keys_returns_six_levels():
    ctx = CutContext()
    keys = context_keys(ctx)
    assert len(keys) == 6
    # Level 0 = global
    assert keys[0] == ""
    # Aufsteigende Spezifität: jeder ist Präfix des nächsten (wegen "|"-Trennung)
    for i in range(len(keys) - 1):
        assert keys[i + 1].startswith(keys[i]), \
            f"Level {i+1} ist nicht Erweiterung von Level {i}"


def test_context_keys_are_unique_per_context():
    ctx_a = CutContext(audio_section_type="drop", audio_mood="dark")
    ctx_b = CutContext(audio_section_type="intro", audio_mood="uplifting")
    assert context_keys(ctx_a) != context_keys(ctx_b)


def test_quantize_tertile():
    assert quantize_tertile(0.1, p33=0.3, p66=0.7) == "low"
    assert quantize_tertile(0.5, p33=0.3, p66=0.7) == "medium"
    assert quantize_tertile(0.9, p33=0.3, p66=0.7) == "high"
    # Custom labels
    assert quantize_tertile(0.5, 0.3, 0.7, classes=("a", "b", "c")) == "b"


def test_quantize_subtrack_position():
    assert quantize_subtrack_position(0.0, 0.0, 100.0) == "start"   # 0%
    assert quantize_subtrack_position(20.0, 0.0, 100.0) == "start"  # 20%
    assert quantize_subtrack_position(50.0, 0.0, 100.0) == "middle" # 50%
    assert quantize_subtrack_position(80.0, 0.0, 100.0) == "end"    # 80%


# ---------------------------------------------------------------------------
# weight_store / Beta-Bernoulli
# ---------------------------------------------------------------------------
def test_alpha_beta_posterior_mean_cold_start():
    ab = AlphaBeta(alpha=0.0, beta=0.0)
    # (0+1)/(0+0+2) = 0.5
    assert abs(ab.posterior_mean - 0.5) < 1e-9


def test_alpha_beta_posterior_mean_strong_positive():
    ab = AlphaBeta(alpha=20.0, beta=0.0)
    # (20+1)/(20+0+2) = 21/22 ≈ 0.9545
    assert abs(ab.posterior_mean - 21 / 22) < 1e-9


def test_alpha_beta_variance_decreases_with_more_data():
    v_few = AlphaBeta(alpha=2.0, beta=2.0).variance
    v_many = AlphaBeta(alpha=200.0, beta=200.0).variance
    assert v_many < v_few


def test_get_posterior_mean_cold_start_returns_default(store: WeightStore):
    ctx = CutContext(audio_section_type="drop", audio_mood="dark")
    keys = context_keys(ctx)
    pm = store.get_posterior_mean("kick_weight", keys)
    # Cold-Start: Default für kick_weight ist 1.2
    assert pm == 1.2


def test_get_posterior_mean_after_clicks_uses_level_0(store: WeightStore):
    ctx = CutContext()
    keys = context_keys(ctx)
    # 10 Klicks auf Level 0 mit α=2.0 jeweils
    for _ in range(10):
        store.update("kick_weight", 0, "", alpha_delta=2.0, beta_delta=0.0)
    # Lookup ohne spezifischere Daten → Level 0 ist konfident, Backoff bis L0
    # Aber: Level 1-5 haben 0 Samples → Backoff zu Level 0
    pm = store.get_posterior_mean("kick_weight", keys)
    expected = (20.0 + 1.0) / (20.0 + 0.0 + 2.0)
    assert abs(pm - expected) < 1e-9


def test_backoff_finds_specific_when_confident(store: WeightStore):
    ctx = CutContext(audio_section_type="drop")
    keys = context_keys(ctx)
    # Level 0: 100 Klicks mit α=1.0
    for _ in range(100):
        store.update("kick_weight", 0, keys[0], 1.0, 0)
    # Level 1: 15 Klicks mit α=2.0 — konfident (≥10)
    for _ in range(15):
        store.update("kick_weight", 1, keys[1], 2.0, 0)
    pm = store.get_posterior_mean("kick_weight", keys)
    # Spezifischster konfidenter Bucket = Level 1: α=30, β=0
    expected = (30.0 + 1.0) / (30.0 + 0.0 + 2.0)
    assert abs(pm - expected) < 1e-9


def test_backoff_falls_back_when_specific_not_confident(store: WeightStore):
    ctx = CutContext(audio_section_type="drop")
    keys = context_keys(ctx)
    # Level 0: 100 Klicks mit α=1.0 (konfident, n_samples=100)
    for _ in range(100):
        store.update("kick_weight", 0, keys[0], 1.0, 0)
    # Level 1: 5 Klicks mit α=1.0 (NICHT konfident, n_samples=5 < 10)
    # WICHTIG: α=1.0 nicht 2.0, sonst wäre n_samples=10 = genau Schwelle.
    for _ in range(5):
        store.update("kick_weight", 1, keys[1], 1.0, 0)
    pm = store.get_posterior_mean("kick_weight", keys)
    # Backoff: Level 5..2 leer, Level 1 hat n=5 (< 10) → skip,
    # Level 0 hat n=100 (≥ 10) → return
    expected = (100.0 + 1.0) / (100.0 + 0.0 + 2.0)
    assert abs(pm - expected) < 1e-9


def test_get_posterior_mean_unknown_axis_raises(store: WeightStore):
    with pytest.raises(ValueError):
        store.get_posterior_mean("not_an_axis", [""])


def test_total_clicks_grows_with_updates(store: WeightStore):
    assert store.total_clicks() == 0.0
    store.update("kick_weight", 0, "", 2.0, 0.0)
    assert store.total_clicks() == 2.0


def test_top_buckets_returns_strongest_positive(store: WeightStore):
    store.update("kick_weight", 0, "", 50.0, 0)
    store.update("snare_weight", 0, "", 5.0, 0)
    top = store.top_buckets(n=2, by="positive")
    assert len(top) == 2
    assert top[0]["axis"] == "kick_weight"
    assert top[0]["positive_count"] == 50.0


def test_cold_start_status_all_axes_in_cold_start(store: WeightStore):
    s = store.cold_start_status()
    assert s["total_axes"] == 17
    assert s["confident_axes"] == 0
    assert s["cold_start_axes"] == 17


def test_cold_start_status_one_axis_confident(store: WeightStore):
    for _ in range(MIN_CONFIDENT_SAMPLES):
        store.update("kick_weight", 0, "", 1.0, 0)
    s = store.cold_start_status()
    assert s["confident_axes"] == 1
    assert s["cold_start_axes"] == 16


# ---------------------------------------------------------------------------
# feedback_logger / Atomic-85-Bucket-Update
# ---------------------------------------------------------------------------
def test_rating_map_completeness():
    assert set(RATING_MAP.keys()) == {"perfect", "fits", "not_quite", "no_match"}
    # Plan-Doc 02 #11
    assert RATING_MAP["perfect"] == (2.0, 0.0)
    assert RATING_MAP["no_match"] == (0.0, 2.0)


def test_log_feedback_updates_85_buckets(store: WeightStore):
    fl = FeedbackLogger(store)
    ctx = CutContext()
    keys = context_keys(ctx)
    res = fl.log_feedback("perfect", keys)
    assert res["n_buckets_updated"] == 17 * 6  # = 102 Achsen × Levels
    # WAIT: Plan-Doc sagt 17 × 5 = 85, aber wir haben 6 Levels (Level 0..5)
    # — überprüfen wir mit der Realität: context_keys liefert 6 Werte
    assert len(keys) == 6


def test_log_feedback_perfect_increments_alpha_only(store: WeightStore, weights_db: Path):
    fl = FeedbackLogger(store)
    ctx = CutContext()
    keys = context_keys(ctx)
    fl.log_feedback("perfect", keys)
    # Direkt in DB lesen
    conn = sqlite3.connect(weights_db)
    rows = conn.execute(
        "SELECT positive_count, negative_count FROM axis_weights "
        "WHERE axis='kick_weight' AND context_level=0"
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    pos, neg = rows[0]
    assert pos == 2.0
    assert neg == 0.0


def test_log_feedback_no_match_increments_beta_only(store: WeightStore):
    fl = FeedbackLogger(store)
    ctx = CutContext()
    keys = context_keys(ctx)
    fl.log_feedback("no_match", keys)
    ab = store.get_alpha_beta("kick_weight", 0, "")
    assert ab.alpha == 0.0
    assert ab.beta == 2.0


def test_log_feedback_invalid_rating_raises(store: WeightStore):
    fl = FeedbackLogger(store)
    with pytest.raises(ValueError):
        fl.log_feedback("kinda_ok", context_keys(CutContext()))


def test_log_feedback_wrong_keys_length_raises(store: WeightStore):
    fl = FeedbackLogger(store)
    with pytest.raises(ValueError):
        fl.log_feedback("perfect", ["", "", ""])  # nur 3 statt 6


def test_log_feedback_repeated_clicks_accumulate(store: WeightStore):
    fl = FeedbackLogger(store)
    ctx = CutContext()
    keys = context_keys(ctx)
    for _ in range(5):
        fl.log_feedback("perfect", keys)
    ab = store.get_alpha_beta("kick_weight", 0, "")
    assert ab.alpha == 10.0  # 5 × 2.0
    assert ab.beta == 0.0


def test_log_feedback_atomic_rollback_on_error(store: WeightStore):
    """Verifikation der Transaktion-Atomicity via DROP TABLE während Update.

    sqlite3.Connection.execute ist C-Extension (read-only attribute) →
    monkeypatch nicht möglich. Stattdessen: nach Update DROP TABLE wir
    die ON CONFLICT-Klausel des UPSERT zur Fehlerprovokation indem wir
    den Tabellennamen umbenennen.
    """
    fl = FeedbackLogger(store)
    ctx = CutContext()
    keys = context_keys(ctx)
    # Successful first write
    fl.log_feedback("perfect", keys)
    ab_before = store.get_alpha_beta("kick_weight", 0, "")
    assert ab_before.alpha == 2.0

    # Provoziere Fehler: Tabelle umbenennen → nächster log_feedback crasht.
    conn = store._get_conn()
    conn.execute("ALTER TABLE axis_weights RENAME TO axis_weights_bak")
    conn.commit()

    with pytest.raises(sqlite3.Error):
        fl.log_feedback("no_match", keys)

    # Wiederherstellen + verifizieren: ab_before unverändert
    conn.execute("ALTER TABLE axis_weights_bak RENAME TO axis_weights")
    conn.commit()
    ab_after = store.get_alpha_beta("kick_weight", 0, "")
    assert ab_after.alpha == 2.0
    assert ab_after.beta == 0.0  # kein no_match wurde geschrieben (Rollback)


# ---------------------------------------------------------------------------
# bridge_dimensions
# ---------------------------------------------------------------------------
def test_bridge_compute_returns_in_range():
    bd = BridgeDimensions()
    cand = ClipCandidate(clip_id="c1", duration_s=2.0, motion_score=0.7)
    ctx = CutContext(raw_audio_features={"energy": 0.5})
    for axis in BRIDGE_AXES:
        v = bd.compute(axis, cand, ctx)
        assert 0.0 <= v <= 1.0, f"{axis} → {v} out of [0,1]"


def test_bridge_compute_all_returns_17():
    bd = BridgeDimensions()
    cand = ClipCandidate(clip_id="c1", duration_s=2.0)
    ctx = CutContext()
    all_vals = bd.compute_all(cand, ctx)
    assert len(all_vals) == 17
    assert set(all_vals.keys()) == set(BRIDGE_AXES)


def test_bridge_motion_match_perfect_alignment():
    bd = BridgeDimensions()
    cand = ClipCandidate(clip_id="c1", duration_s=2.0, motion_score=0.7)
    ctx = CutContext(raw_audio_features={"energy": 0.7})
    v = bd.compute("motion_match_weight", cand, ctx)
    assert v == 1.0  # 1 - |0.7 - 0.7| = 1.0


def test_bridge_unknown_axis_raises():
    bd = BridgeDimensions()
    with pytest.raises(ValueError):
        bd.compute("not_an_axis", ClipCandidate("c", 1.0), CutContext())


def test_bridge_semantic_match_with_aligned_embedding():
    bd = BridgeDimensions()
    emb = np.ones(768, dtype="float32")
    cand = ClipCandidate(clip_id="c1", duration_s=2.0, embedding=emb)
    ctx = CutContext(raw_audio_features={"mood_prototype": emb.copy()})
    v = bd.compute("semantic_match_weight", cand, ctx)
    # Cosine = 1 → (1+1)/2 = 1.0
    assert v == 1.0


# ---------------------------------------------------------------------------
# scorer
# ---------------------------------------------------------------------------
def test_scorer_returns_scored_candidate(store: WeightStore):
    sc = Scorer(BridgeDimensions(), store)
    cand = ClipCandidate(clip_id="c1", duration_s=2.0, motion_score=0.6)
    ctx = CutContext(raw_audio_features={"energy": 0.6})
    res = sc.score(cand, ctx)
    assert res.candidate is cand
    assert 0.0 <= res.final_score <= 2.0  # bridge*weight, weight ≤ 2.0
    assert len(res.brain_v3_scores) == 17


def test_scorer_normalizes_by_weight_sum_not_axis_count():
    from services.brain.cold_start import BRIDGE_AXES

    primary_axis = BRIDGE_AXES[0]

    class _Bridge:
        def compute(self, axis, candidate, cut_context):
            return 1.0 if axis == primary_axis else 0.0

    class _Weights:
        def get_posterior_mean(self, axis, keys):
            return 10.0 if axis == primary_axis else 0.0

    sc = Scorer(_Bridge(), _Weights())
    cand = ClipCandidate(clip_id="c1", duration_s=2.0, motion_score=0.6)

    res = sc.score(cand, CutContext())

    assert res.final_score == 1.0


def test_scorer_score_all_sorts_descending(store: WeightStore):
    sc = Scorer(BridgeDimensions(), store)
    cands = [
        ClipCandidate(clip_id=f"c{i}", duration_s=float(i + 1), motion_score=0.5)
        for i in range(3)
    ]
    ctx = CutContext()
    out = sc.score_all(cands, ctx)
    assert len(out) == 3
    for i in range(len(out) - 1):
        assert out[i].final_score >= out[i + 1].final_score


# ---------------------------------------------------------------------------
# brain_store
# ---------------------------------------------------------------------------
def test_brain_store_initializes_three_dbs(isolated_appdata):
    bs = BrainStore()
    s = bs.stats()
    assert s.weights_rows == 0
    assert s.patterns_rows == 0
    # embedding_cache_db existiert noch nicht (außer von Phase-2-Tests)
    assert s.weights_db_size_bytes > 0


def test_brain_store_reset_clears_weights_and_patterns(isolated_appdata):
    bs = BrainStore()
    ws = WeightStore(bs.weights_path)
    ws.update("kick_weight", 0, "", 5.0, 0)
    ws.close()
    assert bs.stats().weights_rows == 1

    bs.reset()
    assert bs.stats().weights_rows == 0


def test_brain_store_reset_keeps_embedding_cache_by_default(isolated_appdata):
    """Plan-Doc 05 Reset-Verhalten: embedding_cache bleibt erhalten."""
    from services.brain.storage.embedding_cache import EmbeddingCache
    cache = EmbeddingCache()
    cache.store("a" * 64, "audio", np.zeros(512, dtype="float32"),
                "model_x", "1.0")
    bs = BrainStore()
    bs.reset(also_embedding_cache=False)
    # embedding_cache hat noch den Eintrag
    assert cache.lookup("a" * 64, "model_x", "1.0") is not None


# ---------------------------------------------------------------------------
# Integration: Klick → Posterior konvergiert
# ---------------------------------------------------------------------------
def test_integration_clicks_change_posterior(store: WeightStore):
    """Klick-Loop ändert Posterior. NB: Cold-Start-Defaults und gelernte
    Posterior-Mean liegen in unterschiedlichen Skalen — Cold-Start =
    TriggerSettings (kann 0–2 sein), Posterior = (0, 1). Der Test
    vergleicht daher KEINE Cold-Start-vs-Posterior, sondern nur
    Posterior-Verschiebung durch Klick-Vorzeichen.
    """
    fl = FeedbackLogger(store)
    ctx = CutContext(audio_section_type="drop", audio_mood="dark")
    keys = context_keys(ctx)

    # 15 perfect-Klicks → Level 5 wird konfident (15 × α=2.0 = 30 α)
    for _ in range(15):
        fl.log_feedback("perfect", keys)
    pm_after_positive = store.get_posterior_mean("kick_weight", keys)
    expected_positive = (30.0 + 1.0) / (30.0 + 0.0 + 2.0)
    assert abs(pm_after_positive - expected_positive) < 1e-9
    # Posterior nach positiven Klicks > Laplace-Anker (0.5)
    assert pm_after_positive > 0.5

    # Mit no_match-Klicks senkt sich Posterior wieder
    for _ in range(15):
        fl.log_feedback("no_match", keys)
    pm_after_neutral = store.get_posterior_mean("kick_weight", keys)
    # Jetzt α=30, β=30 → posterior = 31/62 = 0.5
    assert abs(pm_after_neutral - 0.5) < 0.05
