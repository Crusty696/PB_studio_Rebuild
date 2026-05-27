"""B-336 GPU-Benchmark: SigLIP fp16 vs fp32 auf der GTX 1060.

Hintergrund: ``services/model_manager.py`` (load_siglip / Vision) erzwingt
``torch.float16`` fuer alles ausser CPU. Pascal (GTX 1060, SM 6.1) hat keinen
echten fp16-Tensor-Durchsatz -> fp16 ist emuliert + potenziell NaN-anfaellig.
Dieser Lauf liefert die fehlende Entscheidungsgrundlage fuer B-336:

  1. Treten in fp16 NaN/Inf in den Embeddings auf? (Korrektheit)
  2. Wie hoch ist der VRAM-Peak fp16 vs fp32? Passt fp32 in 6 GB neben den
     Brain-Modellen? (OOM-Risiko)

Ergebnis -> Entscheidung: fp32 ODER fp16 + NaN-Guard.

GPU-Hartregel: ausschliesslich cuda:0 (GTX 1060). Kein anderer Backend.

Nutzung (im conda-env pb-studio):
    python tools/diag_b336_siglip_precision.py
    python tools/diag_b336_siglip_precision.py --image "C:\\pfad\\keyframe.jpg"
    python tools/diag_b336_siglip_precision.py --model google/siglip-so400m-patch14-384 --batch 8
"""
from __future__ import annotations

import argparse
import gc
import sys


def _human_gb(num_bytes: float) -> str:
    return f"{num_bytes / (1024 ** 3):.3f} GB"


def _build_pixel_values(processor, image_path: str | None, batch: int):
    from PIL import Image
    import numpy as np

    if image_path:
        img = Image.open(image_path).convert("RGB")
    else:
        # Deterministisches Pseudo-Bild — reicht fuer NaN-/VRAM-Messung.
        rng = np.random.default_rng(42)
        arr = (rng.random((384, 384, 3)) * 255).astype("uint8")
        img = Image.fromarray(arr, mode="RGB")
    inputs = processor(images=[img] * batch, return_tensors="pt")
    return inputs["pixel_values"]


def _run_one(model_id: str, dtype, device: str, pixel_values_cpu, label: str) -> dict:
    import torch
    from transformers import AutoModel

    torch.cuda.empty_cache()
    gc.collect()
    torch.cuda.reset_peak_memory_stats(device)

    model = AutoModel.from_pretrained(model_id, torch_dtype=dtype)  # nosec B615
    model.to(device)
    model.eval()

    pixel_values = pixel_values_cpu.to(device=device, dtype=dtype)

    with torch.no_grad():
        feats = model.get_image_features(pixel_values=pixel_values)

    torch.cuda.synchronize(device)

    feats_f32 = feats.float()
    n_nan = int(torch.isnan(feats_f32).sum().item())
    n_inf = int(torch.isinf(feats_f32).sum().item())
    peak_alloc = torch.cuda.max_memory_allocated(device)
    peak_reserved = torch.cuda.max_memory_reserved(device)

    result = {
        "label": label,
        "shape": tuple(feats.shape),
        "dtype": str(feats.dtype),
        "nan": n_nan,
        "inf": n_inf,
        "peak_alloc": peak_alloc,
        "peak_reserved": peak_reserved,
        "norm_mean": float(feats_f32.norm(dim=-1).mean().item()),
    }

    del feats, feats_f32, pixel_values, model
    gc.collect()
    torch.cuda.empty_cache()
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="B-336 SigLIP fp16 vs fp32 Benchmark (cuda:0)")
    ap.add_argument("--model", default="google/siglip-so400m-patch14-384",
                    help="HF-Model-ID (Default = App-SigLIP aus model_manager.load_siglip)")
    ap.add_argument("--image", default=None, help="Optionaler Keyframe-Pfad; sonst Pseudo-Bild")
    ap.add_argument("--batch", type=int, default=8, help="Batch-Groesse (Default 8 = Embedder-Default)")
    args = ap.parse_args()

    import torch
    if not torch.cuda.is_available():
        print("FEHLER: CUDA nicht verfuegbar. B-336 ist ein GPU-Benchmark — auf der GTX 1060 laufen lassen.")
        return 2
    device = "cuda:0"
    print(f"GPU: {torch.cuda.get_device_name(0)}  capability={torch.cuda.get_device_capability(0)}")
    print(f"Model: {args.model}  batch={args.batch}")

    from transformers import AutoProcessor
    processor = AutoProcessor.from_pretrained(args.model, use_fast=False)  # nosec B615
    pixel_values_cpu = _build_pixel_values(processor, args.image, args.batch)

    results = []
    for label, dtype in (("fp16", torch.float16), ("fp32", torch.float32)):
        print(f"\n--- {label} ---")
        try:
            r = _run_one(args.model, dtype, device, pixel_values_cpu, label)
            results.append(r)
            print(f"  shape={r['shape']} dtype={r['dtype']} NaN={r['nan']} Inf={r['inf']} "
                  f"emb-norm(mean)={r['norm_mean']:.4f}")
            print(f"  VRAM peak: alloc={_human_gb(r['peak_alloc'])}  reserved={_human_gb(r['peak_reserved'])}")
        except RuntimeError as e:
            print(f"  RuntimeError ({label}): {e}")
            results.append({"label": label, "error": str(e)})

    print("\n================ B-336 VERDIKT ================")
    fp16 = next((r for r in results if r.get("label") == "fp16"), {})
    fp32 = next((r for r in results if r.get("label") == "fp32"), {})

    fp16_bad = bool(fp16.get("nan") or fp16.get("inf")) or "error" in fp16
    if fp16_bad:
        print("fp16: NaN/Inf bzw. Fehler aufgetreten -> fp16 ist auf dieser Pascal-Karte UNSICHER.")
    else:
        print("fp16: keine NaN/Inf -> numerisch unauffaellig.")

    if "error" in fp32:
        print(f"fp32: OOM/Fehler ({fp32['error']}) -> fp32 passt NICHT in 6 GB. Empfehlung: fp16 + NaN-Guard.")
    elif fp16_bad:
        if fp32.get("peak_reserved", 0) < 5.0 * (1024 ** 3):
            print("Empfehlung: auf fp32 umstellen (NaN-frei und VRAM-Peak < 5 GB).")
        else:
            print("fp32 VRAM-Peak hoch (>5 GB) -> OOM-Risiko neben Brain-Modellen. "
                  "Empfehlung: fp16 + NaN-Guard (Fallback fp32 nur fuer dieses Modell).")
    else:
        print("fp16 ist numerisch ok UND spart VRAM -> bestehendes fp16-Verhalten beibehalten, "
              "B-336 ggf. als wontfix/observed schliessen.")
    print("Zahlen oben an David / ins Vault (B-336) zurueckmelden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
