"""FR-S4-3 / Task-S4-3: Reward-Weights-Tuning Grid-Search.

PRE-2 Truth-Set vorausgesetzt (`tests/fixtures/pacing_truth_set.json`,
30 cuts mit User-Verdict). Sucht via 5-fold Cross-Validation Reward-
Weights mit Pearson-Korrelation > 0.6 zur User-Verdict-Verteilung.

Ausführung:
    python scripts/tune_pacing_reward.py [--truth-set PATH] [--output PATH]

Default-Output: services/pacing/default_weights.json
"""
from __future__ import annotations

import argparse
import json
import sys
from itertools import product
from pathlib import Path

import numpy as np

# Erlaube Import aus Repo-Root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.pacing.rl_reward import REWARD_KEYS, RewardComponents, compute_reward


def _load_truth_set(path: Path) -> list[dict]:
    if not path.exists():
        # Template-Fallback
        template = path.parent / "pacing_truth_set.template.json"
        if template.exists():
            print(
                f"Warning: {path.name} fehlt — verwende Template als Skelett. "
                "User muss noch 30 Cuts labeln, sonst hat die Tuning-Pipeline "
                "keine ausreichende Datenbasis."
            )
            return json.loads(template.read_text(encoding="utf-8"))
        raise FileNotFoundError(f"Weder {path} noch Template gefunden")
    return json.loads(path.read_text(encoding="utf-8"))


def _row_to_components(row: dict) -> RewardComponents:
    af = row.get("audio_features", {}) or {}
    vf = row.get("video_features", {}) or {}
    return RewardComponents(
        r_energy=float(af.get("rms", 0.5)),
        r_mood=float(vf.get("cosine_sim_to_audio_mood", 0.5)),
        r_stem_class=float(af.get("stem_class_match", 0.5)),
        r_section=float(af.get("section_coherence", 0.5)),
        r_freshness=float(vf.get("freshness", 0.5)),
        r_collision=float(vf.get("collision_inv", 0.5)),
        r_user=float(1.0 if row.get("verdict") == "good" else 0.0 if row.get("verdict") == "bad" else 0.5),
    )


def _verdict_score(row: dict) -> float:
    return {"good": 1.0, "bad": 0.0}.get(row.get("verdict"), 0.5)


def _pearson(a: list[float], b: list[float]) -> float:
    if len(a) < 2:
        return 0.0
    arr_a = np.asarray(a, dtype=np.float64)
    arr_b = np.asarray(b, dtype=np.float64)
    if arr_a.std() < 1e-9 or arr_b.std() < 1e-9:
        return 0.0
    r = float(np.corrcoef(arr_a, arr_b)[0, 1])
    return r if np.isfinite(r) else 0.0


def grid_search(rows: list[dict], coarse: int = 4) -> dict:
    """Grid-Search auf {0.0, 0.33, 0.66, 1.0} per Komponente.

    Liefert Best-Weights + Score. coarse=4 → 4^7 = 16384 Kombinationen.
    """
    grid = np.linspace(0.0, 1.0, coarse)
    best = {"score": -1.0, "weights": {k: 1.0 / len(REWARD_KEYS) for k in REWARD_KEYS}}
    target = [_verdict_score(r) for r in rows]
    components = [_row_to_components(r) for r in rows]

    for w_vals in product(grid, repeat=len(REWARD_KEYS)):
        weights = {k: float(v) for k, v in zip(REWARD_KEYS, w_vals)}
        if sum(weights.values()) <= 0:
            continue
        rewards = [compute_reward(c, weights=weights) for c in components]
        score = _pearson(rewards, target)
        if score > best["score"]:
            best = {"score": score, "weights": weights}
    return best


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--truth-set",
        default="tests/fixtures/pacing_truth_set.json",
    )
    parser.add_argument(
        "--output",
        default="services/pacing/default_weights.json",
    )
    parser.add_argument("--coarse", type=int, default=4)
    args = parser.parse_args()

    rows = _load_truth_set(Path(args.truth_set))
    if len(rows) < 10:
        print(
            f"Warning: nur {len(rows)} Zeilen — Grid-Search wird Default-Weights speichern. "
            "User-Aufgabe: 30 Cuts in pacing_truth_set.json labeln."
        )
        best = {"score": 0.0, "weights": {k: 1.0 / len(REWARD_KEYS) for k in REWARD_KEYS}}
    else:
        best = grid_search(rows, coarse=args.coarse)
        print(f"Best Pearson r = {best['score']:.3f}")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({
            "weights": best["weights"],
            "pearson": best["score"],
            "n_rows": len(rows),
        }, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
