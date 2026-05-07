"""Brain V3 Phase 3 reset smoke.

Verifies BrainV3Service two-step reset:
- token request
- token-confirmed reset
- weights.db and patterns.db emptied
- cold-start fallback visible in stats

Default uses isolated temp APPDATA. With --live, real APPDATA DBs are backed up
and restored unless --keep-reset is set.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def _configure_appdata(args: argparse.Namespace) -> Path | None:
    if args.live:
        return None
    tmp = Path(tempfile.mkdtemp(prefix="pb-brain-v3-reset-"))
    os.environ["APPDATA"] = str(tmp / "Roaming")
    return tmp


def _backup_files(paths: list[Path], backup_dir: Path) -> dict[str, str | None]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    backups: dict[str, str | None] = {}
    for path in paths:
        if path.exists():
            backup = backup_dir / path.name
            shutil.copy2(path, backup)
            backups[str(path)] = str(backup)
        else:
            backups[str(path)] = None
    return backups


def _restore_files(backups: dict[str, str | None]) -> None:
    for target_raw, backup_raw in backups.items():
        target = Path(target_raw)
        if backup_raw is None:
            target.unlink(missing_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_raw, target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use real APPDATA Brain V3 DBs. Default uses isolated temp APPDATA.",
    )
    parser.add_argument(
        "--keep-reset",
        action="store_true",
        help="With --live, do not restore weights/patterns backups after smoke.",
    )
    args = parser.parse_args(argv)

    tmp_root = _configure_appdata(args)

    from services.brain_v3.brain_v3_service import BrainV3Service
    from services.brain_v3.schemas.brain_v3_schemas import FeedbackRequest, ResetRequest
    from services.brain_v3.storage.brain_store import BrainStore
    from services.brain_v3.storage.embedding_cache import EmbeddingCache

    svc = BrainV3Service()
    db_paths = [svc._brain_store.weights_path, svc._brain_store.patterns_path]
    backup_dir = Path(tempfile.mkdtemp(prefix="pb-brain-v3-reset-backup-"))
    backups = _backup_files(db_paths, backup_dir) if args.live else {}
    restored = False

    try:
        seed = svc.feedback(FeedbackRequest(cut_id=1, rating="perfect"))
        before_reset = svc.stats()

        token_response = svc.reset(ResetRequest())
        reset_response = svc.reset(
            ResetRequest(confirmation_token=token_response.confirmation_token)
        )
        after_reset = svc.stats()
        # Isolated APPDATA starts empty; health_check expects Phase-2 cache schema.
        EmbeddingCache()
        health = BrainStore().health_check()

        checks = {
            "seed_updated_102_buckets": seed.n_buckets_updated == 102,
            "pre_reset_has_rows": before_reset.total_clicks > 0,
            "token_required_first": token_response.status == "token_required"
            and bool(token_response.confirmation_token),
            "reset_done_second": reset_response.status == "reset_done",
            "weights_cleared": after_reset.total_clicks == 0,
            "cold_start_after_reset": after_reset.learned_axes == 0
            and after_reset.cold_start_axes == 17,
            "health_ok_after_reset": health.weights_ok
            and health.patterns_ok
            and health.embedding_cache_ok,
        }

        result = {
            "mode": "live" if args.live else "isolated",
            "tmp_root": str(tmp_root) if tmp_root else None,
            "backup_dir": str(backup_dir) if args.live else None,
            "before_reset": before_reset.model_dump(),
            "after_reset": after_reset.model_dump(),
            "reset_response": reset_response.model_dump(),
            "health": health.__dict__,
            "checks": checks,
            "ok": all(checks.values()),
        }
    finally:
        if args.live and not args.keep_reset:
            _restore_files(backups)
            restored = True

    result["restored"] = restored
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
