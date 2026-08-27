from types import SimpleNamespace

import numpy as np

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


def _clip(clip_id: int) -> ClipFeatures:
    return ClipFeatures(
        clip_id=clip_id,
        scene_id=clip_id * 10,
        role="action",
        mood_refined="energetic",
        style_bucket_id=1,
        motion_score=0.6,
        embedding=np.ones(4, dtype=np.float32),
    )


class _EqualReranker:
    def rerank(self, scored, ctx, recent_clip_ids=None):
        return [
            SimpleNamespace(
                clip_id=clip.clip_id,
                final_score=0.75,
                brain_v3_scores={},
                no_signal_axes=frozenset(),
            )
            for clip, _score, _contribs in scored
        ]


def test_pipeline_tie_break_is_independent_of_candidate_input_order(tmp_path) -> None:
    def choose(order: list[int]) -> int:
        pipeline = PacingPipeline(
            rules_path=tmp_path / "missing_rules.yaml",
            use_brain_v3=True,
            brain_v3_reranker=_EqualReranker(),
        )
        result = pipeline.select_best([_clip(i) for i in order], _context())
        assert result.chosen is not None
        return result.chosen.clip_id

    assert choose([2, 1]) == choose([1, 2]) == 1


def test_vector_search_tie_break_uses_canonical_composite_id(tmp_path) -> None:
    import services.vector_db_service as vector_module

    vector_module._instance = None
    service = vector_module.VectorDBService(tmp_path / "vectors.db")
    embedding = np.ones(vector_module.EMBEDDING_DIM, dtype=np.float32)
    try:
        service.add_embedding(2, "b.mp4", 0, 0.0, 1.0, embedding)
        service.add_embedding(1, "a.mp4", 0, 0.0, 1.0, embedding)
        results = service.search(embedding, top_k=2)
    finally:
        vector_module._instance = None

    assert [result["id"] for result in results] == [1_000_000, 2_000_000]
