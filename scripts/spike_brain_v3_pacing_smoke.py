"""Brain V3 Phase 4 pacing integration smoke.

Verifies:
- BrainV3Service.suggest() returns brain_v3_scores
- BrainV3Service.feedback() updates 102 buckets
- BrainV3Service.stats() sees learning
- PacingPipeline(use_brain_v3=True) runs Stage-4 reranker path
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def _configure_appdata(args: argparse.Namespace) -> Path | None:
    if args.live:
        return None
    tmp = Path(tempfile.mkdtemp(prefix="pb-brain-v3-pacing-"))
    os.environ["APPDATA"] = str(tmp / "Roaming")
    return tmp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use real APPDATA Brain V3 DBs. Default uses isolated temp APPDATA.",
    )
    args = parser.parse_args(argv)

    tmp_root = _configure_appdata(args)
    project_root = None
    if tmp_root is not None:
        project_root = tmp_root / "project"
        project_root.mkdir(parents=True, exist_ok=True)

    from services.brain.brain_v3_service import BrainV3Service
    from services.brain.schemas.brain_v3_schemas import (
        FeedbackRequest,
        SuggestRequest,
    )
    from services.pacing.pipeline import PacingPipeline
    from services.pacing.scorer import AudioContext, ClipFeatures

    svc = BrainV3Service(project_root=project_root)

    suggest = svc.suggest(
        SuggestRequest(audio_clip_id=1, video_clip_ids=[101, 102, 103], n_top=3)
    )
    feedback = svc.feedback(FeedbackRequest(cut_id=1, rating="perfect"))
    stats = svc.stats()

    emb_a = np.linspace(0.1, 0.9, 16, dtype=np.float32)
    emb_b = np.linspace(0.9, 0.1, 16, dtype=np.float32)
    emb_c = np.ones(16, dtype=np.float32) * 0.5
    candidates = [
        ClipFeatures(
            clip_id=101,
            scene_id=201,
            role="hero",
            mood_refined="dark",
            style_bucket_id=1,
            motion_score=0.8,
            embedding=emb_a,
        ),
        ClipFeatures(
            clip_id=102,
            scene_id=202,
            role="action",
            mood_refined="aggressive",
            style_bucket_id=2,
            motion_score=0.7,
            embedding=emb_b,
        ),
        ClipFeatures(
            clip_id=103,
            scene_id=203,
            role="detail",
            mood_refined="calm",
            style_bucket_id=3,
            motion_score=0.2,
            embedding=emb_c,
        ),
    ]
    ctx = AudioContext(
        at_timestamp_sec=32.0,
        at_beat_idx=64,
        at_section_type="drop",
        at_bpm=128.0,
        at_energy=0.8,
        at_key="Am",
        at_key_confidence=0.9,
        at_harmonic_tension=0.4,
        at_mood_audio="dramatic",
        at_mood_video=None,
        at_genre="psytrance",
        at_sub_genre="progressive",
        at_spectral_hash="smoke",
        at_groove_template="four_on_floor",
        at_lufs=-12.0,
    )
    t0 = time.perf_counter()
    pacing_baseline = PacingPipeline(use_brain_v3=False).select_best(
        candidates, ctx, recent_clip_ids=[99, 100]
    )
    pacing_baseline_ms = (time.perf_counter() - t0) * 1000.0

    t0 = time.perf_counter()
    pacing = PacingPipeline(use_brain_v3=True).select_best(
        candidates, ctx, recent_clip_ids=[99, 100]
    )
    pacing_brain_ms = (time.perf_counter() - t0) * 1000.0

    t0 = time.perf_counter()
    learning = svc.learning_session(n=15)
    learning_ms = (time.perf_counter() - t0) * 1000.0

    pacing_overhead_ms = pacing_brain_ms - pacing_baseline_ms

    first_cut_scores = (
        suggest.cuts[0].metadata.get("brain_v3_scores", {}) if suggest.cuts else {}
    )
    checks = {
        "suggest_returns_cuts": len(suggest.cuts) == 3,
        "suggest_used_brain_v3": suggest.used_brain_v3 is True,
        "suggest_has_17_scores": len(first_cut_scores) == 17,
        "feedback_updates_102_buckets": feedback.n_buckets_updated == 102,
        "stats_has_clicks": stats.total_clicks > 0,
        "pacing_chose_candidate": pacing.chosen is not None,
        "pacing_used_brain_v3": pacing.rationale.get("used_brain_v3") is True,
        "pacing_has_brain_scores": len(pacing.rationale.get("brain_v3_scores", {})) == 17,
        "pacing_compare_ran": pacing_baseline.chosen is not None and pacing.chosen is not None,
        "pacing_overhead_under_800ms": pacing_overhead_ms < 800.0,
        "learning_session_under_2s": learning_ms < 5000.0,
        "learning_session_returns_at_most_15": len(learning.samples) <= 15,
    }
    result = {
        "mode": "live" if args.live else "isolated",
        "tmp_root": str(tmp_root) if tmp_root else None,
        "suggest": suggest.model_dump(),
        "feedback": feedback.model_dump(),
        "stats": stats.model_dump(),
        "learning_session": learning.model_dump(),
        "timings_ms": {
            "pacing_baseline": pacing_baseline_ms,
            "pacing_brain_v3": pacing_brain_ms,
            "pacing_overhead": pacing_overhead_ms,
            "learning_session": learning_ms,
        },
        "pacing_compare": {
            "baseline": {
                "chosen_clip_id": (
                    pacing_baseline.chosen.clip_id if pacing_baseline.chosen else None
                ),
                "chosen_score": pacing_baseline.rationale.get("chosen_score"),
                "used_brain_v3": pacing_baseline.rationale.get("used_brain_v3"),
            },
            "brain_v3": {
                "chosen_clip_id": pacing.chosen.clip_id if pacing.chosen else None,
                "chosen_score": pacing.rationale.get("chosen_score"),
                "legacy_soft_score": pacing.rationale.get("legacy_soft_score"),
                "brain_v3_final_score": pacing.rationale.get("brain_v3_final_score"),
                "used_brain_v3": pacing.rationale.get("used_brain_v3"),
            },
        },
        "pacing": {
            "chosen_clip_id": pacing.chosen.clip_id if pacing.chosen else None,
            "rationale": pacing.rationale,
        },
        "checks": checks,
        "ok": all(checks.values()),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
