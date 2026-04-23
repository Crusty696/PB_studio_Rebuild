"""
scripts/generate_mood_anchors.py
=================================

One-shot CLI: loads SigLIP text encoder, embeds each mood anchor prompt
from a YAML catalog, and saves the result as a NumPy .npz file.

Usage::

    python scripts/generate_mood_anchors.py
    python scripts/generate_mood_anchors.py --input config/mood_anchors_v1.yaml \\
                                             --output config/mood_anchors.npz

The .npz contains one array per mood name:  ``{mood_name: vector_1152d, ...}``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import numpy as np
import yaml  # type: ignore[import-untyped]

_SIGLIP_MODEL_ID = "google/siglip-so400m-patch14-384"


def _encode_prompts(
    prompts: dict[str, str],
) -> dict[str, np.ndarray]:
    """Return {mood_name: float32 vector (1152,)} for every prompt.

    Uses SigLIP text encoder directly via transformers AutoModel/AutoTokenizer,
    mirroring the pattern in services/video_analysis_service.py:795.
    The ModelManager singleton is skipped here because this is a one-shot
    offline operation that runs outside the Qt application context.
    """
    import torch
    from transformers import AutoModel, AutoTokenizer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading SigLIP text encoder on {device} …")

    tokenizer = AutoTokenizer.from_pretrained(_SIGLIP_MODEL_ID)
    model = AutoModel.from_pretrained(
        _SIGLIP_MODEL_ID,
        torch_dtype=torch.float32,
    )
    model.to(device)
    model.eval()

    results: dict[str, np.ndarray] = {}
    for name, text in prompts.items():
        inputs: dict[str, Any] = tokenizer(
            text, return_tensors="pt", padding="max_length", truncation=True
        )
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model.get_text_features(**inputs)
            # Robust: handle both raw tensor and BaseModelOutputWithPooling
            if not isinstance(outputs, torch.Tensor):
                outputs = (
                    outputs.pooler_output
                    if hasattr(outputs, "pooler_output")
                    else outputs[0]
                )
            vector = outputs.cpu().numpy().astype(np.float32)[0]

        results[name] = vector
        print(f"  encoded: {name}")

    return results


def _print_summary(vectors: dict[str, np.ndarray]) -> None:
    col_w = max(len(n) for n in vectors) + 2
    print(f"\n{'Mood':<{col_w}}  L2 norm")
    print("-" * (col_w + 12))
    for name in sorted(vectors):
        norm = float(np.linalg.norm(vectors[name]))
        print(f"{name:<{col_w}}  {norm:.6f}")
    print()


def main() -> None:
    # Force UTF-8 stdout on Windows so summary table prints cleanly.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Generate SigLIP mood-anchor embeddings from a YAML prompt catalog."
    )
    parser.add_argument(
        "--input",
        default="config/mood_anchors_v1.yaml",
        help="Path to the mood anchor YAML file (default: config/mood_anchors_v1.yaml).",
    )
    parser.add_argument(
        "--output",
        default="config/mood_anchors.npz",
        help="Output .npz path (default: config/mood_anchors.npz).",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"ERROR: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    with input_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    prompts: dict[str, str] = data["anchors"]
    print(f"Loaded {len(prompts)} prompts from {input_path}")
    for name, text in sorted(prompts.items()):
        print(f"  {name}: {text!r}")

    print("\nEncoding prompts via SigLIP …")
    vectors = _encode_prompts(prompts)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # np.savez (not compressed) for deterministic byte output.
    np.savez(str(output_path), **vectors)  # type: ignore[arg-type]
    print(f"Saved {len(vectors)} vectors → {output_path}")

    _print_summary(vectors)


if __name__ == "__main__":
    main()
