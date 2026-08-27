from pathlib import Path
from types import SimpleNamespace

import numpy as np

from services.brain.context_resolver import CutContext, context_keys
from services.brain.feedback_logger import (
    FeedbackLogger,
    axis_contributions_from_rationale,
)
from services.brain.storage.migration_runner import migrate
from services.brain.weight_store import WeightStore
from services.pacing.pipeline import PacingPipeline
from services.pacing.scorer import AudioContext, ClipFeatures


def _context() -> AudioContext:
    return AudioContext(
        at_timestamp_sec=10.0,
        at_beat_idx=20,
        at_section_type="verse",
        at_bpm=128.0,
        at_energy=0.6,
        at_key="A min",
        at_key_confidence=0.8,
        at_harmonic_tension=0.4,
        at_mood_audio="energetic",
        at_mood_video=None,
        at_genre="techno",
        at_sub_genre=None,
        at_spectral_hash="hash",
        at_groove_template="four_on_floor",
        at_lufs=-12.0,
    )


def _clip() -> ClipFeatures:
    return ClipFeatures(
        clip_id=1,
        scene_id=10,
        role="action",
        mood_refined="energetic",
        style_bucket_id=1,
        motion_score=0.6,
        embedding=np.ones(4, dtype=np.float32),
    )


def test_pipeline_rationale_excludes_no_signal_axes_from_credit(tmp_path) -> None:
    class _Reranker:
        def rerank(self, scored, ctx, recent_clip_ids=None):
            return [
                SimpleNamespace(
                    clip_id=1,
                    final_score=0.9,
                    brain_v3_scores={
                        "kick_weight": 0.8,
                        "semantic_match_weight": 0.5,
                    },
                    no_signal_axes=frozenset({"semantic_match_weight"}),
                )
            ]

    pipeline = PacingPipeline(
        rules_path=tmp_path / "missing_rules.yaml",
        use_brain_v3=True,
        brain_v3_reranker=_Reranker(),
    )
    result = pipeline.select_best([_clip()], _context())

    assert result.rationale["brain_v3_no_signal_axes"] == [
        "semantic_match_weight"
    ]
    assert axis_contributions_from_rationale(result.rationale) == {
        "kick_weight": 0.8
    }


def test_explicit_empty_signal_map_writes_no_uniform_credit(tmp_path) -> None:
    db_path = tmp_path / "weights.db"
    migration_dir = (
        Path(__file__).resolve().parents[2]
        / "services"
        / "brain"
        / "storage"
        / "sql_migrations"
        / "weights"
    )
    migrate(db_path, migration_dir)
    store = WeightStore(db_path)
    try:
        diag = FeedbackLogger(store).log_feedback(
            "fits", context_keys(CutContext()), axis_contributions={}
        )
    finally:
        store.close()

    assert diag["credit_mode"] == "weighted"
    assert diag["n_axes_credited"] == 0
    assert diag["n_buckets_updated"] == 0
