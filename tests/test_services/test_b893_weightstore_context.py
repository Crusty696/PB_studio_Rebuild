from types import SimpleNamespace

from services.brain.context_resolver import context_keys
from services.brain.reranker import BrainV3Reranker
from services.feedback_service import build_cut_context_from_decision


class _CapturingScorer:
    def __init__(self) -> None:
        self.contexts = []

    def score(self, candidate, cut_context):
        self.contexts.append(cut_context)
        return SimpleNamespace(final_score=0.5, brain_v3_scores={})


def test_product_reranker_uses_feedback_compatible_motion_and_pace_context() -> None:
    reranker = BrainV3Reranker(weight_store=SimpleNamespace())
    scorer = _CapturingScorer()
    reranker._scorer = scorer

    clips = [
        SimpleNamespace(clip_id=1, motion_score=0.1),
        SimpleNamespace(clip_id=2, motion_score=0.9),
    ]
    audio = SimpleNamespace(
        at_section_type="drop",
        at_mood_audio="dark",
        at_bpm=140.0,
        at_energy=0.8,
    )

    reranker.rerank(
        [(clip, 0.5, {}) for clip in clips],
        audio,
        recent_clip_ids=[99],
    )

    assert len(scorer.contexts) == 2
    for clip, actual_context in zip(clips, scorer.contexts):
        feedback_context = build_cut_context_from_decision(
            {
                "at_section_type": audio.at_section_type,
                "at_mood_audio": audio.at_mood_audio,
                "at_bpm": audio.at_bpm,
                "at_energy": audio.at_energy,
                "clip_motion_score": clip.motion_score,
            }
        )
        assert context_keys(actual_context) == context_keys(feedback_context)

    assert scorer.contexts[0].video_motion_class == "low"
    assert scorer.contexts[1].video_motion_class == "extreme"
    assert {ctx.video_pace_class for ctx in scorer.contexts} == {"fast"}
