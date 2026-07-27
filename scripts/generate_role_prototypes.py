"""
scripts/generate_role_prototypes.py
====================================

One-shot CLI: laedt den SigLIP-Text-Encoder, embedded pro Rolle ein
Prompt-Ensemble aus ``config/role_prototypes_v1.yaml``, mittelt die
Prompt-Vektoren je Rolle, L2-normiert und schreibt
``config/role_prototypes.npz``.

Aufbau bewusst 1:1 nach ``scripts/generate_mood_anchors.py`` (gleiches
Modell, gleiches Ablageformat), erweitert um das Prompt-Ensemble-Muster aus
``services/pacing/shot_type_classifier.py``.

Verwendung::

    python scripts/generate_role_prototypes.py
    python scripts/generate_role_prototypes.py --input config/role_prototypes_v1.yaml \\
                                               --output config/role_prototypes.npz
    python scripts/generate_role_prototypes.py --device cpu

Das ``.npz`` enthaelt ein Array pro Rolle: ``{role_name: vector_1152d, ...}``.
Modell ist fest ``google/siglip-so400m-patch14-384`` — identisch zu dem
Modell, mit dem ``services/vector_db_service.py`` (EMBEDDING_DIM = 1152) die
Szenen-Embeddings erzeugt hat.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import numpy as np
import yaml  # type: ignore[import-untyped]

_SIGLIP_MODEL_ID = "google/siglip-so400m-patch14-384"


def _encode_prompt_ensembles(
    ensembles: dict[str, list[str]],
    device_override: str | None = None,
) -> dict[str, np.ndarray]:
    """Return {role_name: float32 vector (1152,)} — Mittel ueber das Ensemble.

    Nutzt den SigLIP-Text-Tower direkt via transformers, wie
    ``scripts/generate_mood_anchors.py``. Der ModelManager-Singleton wird
    bewusst umgangen: das hier ist ein einmaliger Offline-Lauf ausserhalb
    des Qt-Application-Kontexts.
    """
    import torch
    from transformers import AutoModel, AutoTokenizer

    if device_override:
        device = device_override
    else:
        # Hartregel: einzige zulaessige GPU ist cuda:0 (GTX 1060). Sonst CPU.
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
    print(f"Loading SigLIP text encoder on {device} …")

    tokenizer = AutoTokenizer.from_pretrained(_SIGLIP_MODEL_ID)
    model = AutoModel.from_pretrained(_SIGLIP_MODEL_ID, torch_dtype=torch.float32)
    model.to(device)
    model.eval()

    results: dict[str, np.ndarray] = {}
    for role, prompts in ensembles.items():
        vecs: list[np.ndarray] = []
        for text in prompts:
            inputs: dict[str, Any] = tokenizer(
                text, return_tensors="pt", padding="max_length", truncation=True
            )
            inputs = {k: v.to(device) for k, v in inputs.items()}
            with torch.no_grad():
                outputs = model.get_text_features(**inputs)
                if not isinstance(outputs, torch.Tensor):
                    outputs = (
                        outputs.pooler_output
                        if hasattr(outputs, "pooler_output")
                        else outputs[0]
                    )
                v = outputs.cpu().numpy().astype(np.float32)[0]
            # Vor dem Mitteln normieren, damit kein einzelner Prompt mit
            # zufaellig grosser Norm das Ensemble dominiert.
            n = float(np.linalg.norm(v))
            if n > 0.0:
                v = v / n
            vecs.append(v)

        centroid = np.mean(np.stack(vecs, axis=0), axis=0).astype(np.float32)
        cn = float(np.linalg.norm(centroid))
        if cn > 0.0:
            centroid = centroid / cn
        results[role] = centroid
        print(f"  encoded: {role}  ({len(prompts)} prompts)")

    return results


def _print_summary(vectors: dict[str, np.ndarray]) -> None:
    names = sorted(vectors)
    col_w = max(len(n) for n in names) + 2
    print(f"\n{'Role':<{col_w}}  L2 norm   dim")
    print("-" * (col_w + 20))
    for name in names:
        v = vectors[name]
        print(f"{name:<{col_w}}  {float(np.linalg.norm(v)):.6f}  {v.shape[0]}")

    # Paarweise Cosine — zeigt sofort, ob zwei Rollen zusammenfallen.
    mat = np.stack([vectors[n] for n in names], axis=0)
    mat = mat / np.linalg.norm(mat, axis=1, keepdims=True)
    sims = mat @ mat.T
    print(f"\nPairwise cosine (off-diagonal max = {float(sims[~np.eye(len(names), dtype=bool)].max()):.4f})")
    print(" " * col_w + "  " + "  ".join(f"{n[:7]:>7}" for n in names))
    for i, n in enumerate(names):
        row = "  ".join(f"{sims[i, j]:>7.3f}" for j in range(len(names)))
        print(f"{n:<{col_w}}  {row}")
    print()


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Generate SigLIP role-prototype embeddings from a YAML prompt catalog."
    )
    parser.add_argument(
        "--input",
        default="config/role_prototypes_v1.yaml",
        help="Path to the role prototype YAML (default: config/role_prototypes_v1.yaml).",
    )
    parser.add_argument(
        "--output",
        default="config/role_prototypes.npz",
        help="Output .npz path (default: config/role_prototypes.npz).",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Force device ('cpu' or 'cuda:0'). Default: cuda:0 if available, else cpu.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"ERROR: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    with input_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    raw: dict[str, Any] = data["roles"]
    ensembles: dict[str, list[str]] = {}
    for role, prompts in raw.items():
        if isinstance(prompts, str):
            prompts = [prompts]
        if not prompts:
            print(f"ERROR: role {role!r} has no prompts", file=sys.stderr)
            sys.exit(1)
        ensembles[str(role)] = [str(p) for p in prompts]

    total_prompts = sum(len(v) for v in ensembles.values())
    print(f"Loaded {len(ensembles)} roles / {total_prompts} prompts from {input_path}")

    print("\nEncoding prompts via SigLIP …")
    vectors = _encode_prompt_ensembles(ensembles, device_override=args.device)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(str(output_path), **vectors)  # type: ignore[arg-type]
    print(f"Saved {len(vectors)} role prototypes → {output_path}")

    _print_summary(vectors)


if __name__ == "__main__":
    main()
