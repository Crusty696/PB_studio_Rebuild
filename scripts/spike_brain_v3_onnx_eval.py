"""Phase 6 Brain V3 ONNX export feasibility eval."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.brain.onnx_export import (  # noqa: E402
    evaluate_onnx_environment,
    recommended_next_step,
    run_onnx_cuda_smoke,
)


def run(out_root: Path) -> dict[str, Any]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = out_root / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    result = evaluate_onnx_environment()
    smoke = run_onnx_cuda_smoke(result.get("onnxruntime_providers", []))
    if result["status"] == "ready" and smoke["status"] != "ok":
        result["status"] = "blocked"
        result.setdefault("blockers", []).append(
            f"onnx CUDA smoke failed: {smoke.get('reason', smoke['status'])}"
        )
    result.update(
        {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "out_dir": str(out_dir),
            "out_dir_name": stamp,
            "cuda_smoke": smoke,
            "next_step": recommended_next_step(result),
        }
    )
    (out_dir / "results.json").write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-root",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "spike_brain_v3_onnx_eval",
    )
    args = parser.parse_args()
    result = run(args.out_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"ready", "blocked"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
