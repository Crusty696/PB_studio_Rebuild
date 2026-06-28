"""Brain V3 Phase 3 mock-click smoke.

Verifies the pre-UI feedback path:
- BrainV3Service.feedback()
- FeedbackLogger atomic 17 axes x 6 levels = 102 bucket updates
- weights.db changes
- stats move from cold-start toward learned state after enough clicks
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def _configure_appdata(args: argparse.Namespace) -> Path | None:
    if args.live:
        return None
    tmp = Path(tempfile.mkdtemp(prefix="pb-brain-v3-mock-click-"))
    os.environ["APPDATA"] = str(tmp / "Roaming")
    return tmp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use real APPDATA Brain V3 DBs. Default uses isolated temp APPDATA.",
    )
    parser.add_argument("--clicks", type=int, default=10)
    args = parser.parse_args(argv)

    if args.clicks < 1:
        raise SystemExit("--clicks must be >= 1")

    tmp_root = _configure_appdata(args)

    from services.brain.brain_v3_service import BrainV3Service
    from services.brain.schemas.brain_v3_schemas import FeedbackRequest

    svc = BrainV3Service()
    before = svc.stats()

    responses = []
    for idx in range(args.clicks):
        responses.append(
            svc.feedback(FeedbackRequest(cut_id=idx + 1, rating="perfect"))
        )

    after = svc.stats()
    store_stats = svc._brain_store.stats()

    checks = {
        "all_clicks_update_102_buckets": all(
            r.n_buckets_updated == 102 for r in responses
        ),
        "weights_rows_positive": store_stats.weights_rows > 0,
        "learned_axes_after_10_clicks": (
            after.learned_axes == 17 if args.clicks >= 10 else True
        ),
        "last_feedback_present": after.last_feedback_at is not None,
    }

    result = {
        "mode": "live" if args.live else "isolated",
        "tmp_root": str(tmp_root) if tmp_root else None,
        "clicks": args.clicks,
        "before": before.model_dump(),
        "after": after.model_dump(),
        "store_stats": {
            "weights_rows": store_stats.weights_rows,
            "patterns_rows": store_stats.patterns_rows,
            "embedding_cache_rows": store_stats.embedding_cache_rows,
        },
        "checks": checks,
        "ok": all(checks.values()),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
