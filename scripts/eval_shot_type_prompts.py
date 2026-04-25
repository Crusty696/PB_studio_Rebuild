"""P3.3 / Cycle 11: Confusion-Matrix-Eval für Shot-Type-Classifier.

Lädt manuell gelabelte Clips (Truth-Set-Subset) + ihre SigLIP-Embeddings,
classifiziert sie über shot_type_classifier.classify, vergleicht mit
Ground-Truth, gibt Confusion-Matrix + Macro-F1 aus.

Akzeptanz: Macro-F1 ≥ 0.65.

Verwendung (sobald Truth-Set 50 Clips enthält):
    python scripts/eval_shot_type_prompts.py \\
        --labels tests/fixtures/shot_type_truth_set.json \\
        --embeddings-dir storage/embeddings/

Truth-Set-Schema (`shot_type_truth_set.json`):
    [{"clip_id": 42, "scene_id": 100, "true_class": "vocal_dominant",
      "embedding_path": "embeddings/clip_42_scene_100.npy"}, ...]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def load_truth_set(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(
            f"Truth-Set fehlt: {path}. "
            "Erst 50 Clips manuell labeln (siehe tests/fixtures/"
            "shot_type_truth_set.template.json)."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def load_clip_embedding(emb_path: Path) -> np.ndarray:
    """Lädt ein 1152-dim float32-Embedding aus .npy."""
    arr = np.load(emb_path)
    if arr.dtype != np.float32:
        arr = arr.astype(np.float32)
    return arr


def confusion_matrix(true_labels: list[str], pred_labels: list[str], classes: list[str]) -> np.ndarray:
    """4×4 Matrix: row = true, col = pred."""
    idx = {c: i for i, c in enumerate(classes)}
    n = len(classes)
    matrix = np.zeros((n, n), dtype=np.int32)
    for t, p in zip(true_labels, pred_labels):
        if t in idx and p in idx:
            matrix[idx[t], idx[p]] += 1
    return matrix


def macro_f1(matrix: np.ndarray) -> float:
    """Macro-F1 = mean(F1 per class)."""
    n = matrix.shape[0]
    f1s = []
    for i in range(n):
        tp = matrix[i, i]
        fp = matrix[:, i].sum() - tp
        fn = matrix[i, :].sum() - tp
        if tp + fp == 0:
            precision = 0.0
        else:
            precision = tp / (tp + fp)
        if tp + fn == 0:
            recall = 0.0
        else:
            recall = tp / (tp + fn)
        if precision + recall == 0:
            f1 = 0.0
        else:
            f1 = 2 * precision * recall / (precision + recall)
        f1s.append(f1)
    return float(sum(f1s) / max(1, len(f1s)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--labels",
        default="tests/fixtures/shot_type_truth_set.json",
    )
    parser.add_argument(
        "--embeddings-dir",
        default="storage/embeddings",
    )
    parser.add_argument("--min-f1", type=float, default=0.65)
    args = parser.parse_args()

    truth = load_truth_set(Path(args.labels))
    if len(truth) < 30:
        print(f"Warning: nur {len(truth)} gelabelte Clips — F1-Schätzung wenig zuverlässig.")

    # Centroids brauchen wir aus dem produktiven Code, nicht hier.
    # Hier nur Skelett — finale Implementierung folgt sobald Truth-Set + Embeddings vorhanden.
    print(
        "P3.3 Skelett: Truth-Set hat", len(truth),
        "Einträge. Volle Implementierung wartet auf Embeddings + SigLIP-Centroid-Caching."
    )

    classes = ["vocal_dominant", "drum_dominant", "melody_dominant", "bass_dominant"]
    print(f"Klassen: {classes}")
    print(f"Akzeptanz-Threshold: Macro-F1 ≥ {args.min_f1}")
    print()
    print("TODO (User): 50 Clips manuell labeln + SigLIP-Embeddings exportieren,")
    print("dann diesen Skript erneut laufen lassen für die echte F1-Messung.")


if __name__ == "__main__":
    main()
