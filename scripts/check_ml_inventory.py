
import os
import torch
from pathlib import Path

def check_local_models():
    print("="*60)
    print("   PB STUDIO - LOKALE ML-MODELL INVENTUR")
    print("="*60)

    # 1. HuggingFace Cache (SigLIP, Whisper)
    hf_home = os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface"))
    hub_dir = Path(hf_home) / "hub"
    
    print(f"\n[1/4] HuggingFace Bestände ({hub_dir}):")
    if hub_dir.exists():
        models = list(hub_dir.glob("models--*"))
        if not models:
            print("  ❌ Keine HuggingFace Modelle gefunden.")
        for m in models:
            name = str(m.name).replace("models--", "").replace("--", "/")
            print(f"  ✅ Gefunden: {name}")
    else:
        print("  ❌ HuggingFace Cache-Verzeichnis existiert nicht.")

    # 2. Demucs Weights
    demucs_dir = Path(os.path.expanduser("~/.cache/torch/hub/checkpoints"))
    print(f"\n[2/4] Demucs/TorchHub Gewichte ({demucs_dir}):")
    if demucs_dir.exists():
        weights = list(demucs_dir.glob("*.th"))
        if not weights:
            print("  ❌ Keine Demucs-Weights gefunden.")
        for w in weights:
            print(f"  ✅ Gefunden: {w.name}")
    else:
        print("  ❌ TorchHub Cache existiert nicht.")

    # 3. beat_this Weights
    bt_path = Path("bin/models/beat_this/final0")
    print(f"\n[3/4] Beat-Analyse (beat_this):")
    if bt_path.exists():
        print(f"  ✅ Gefunden: {bt_path}")
    else:
        print("  ❌ beat_this Gewichte fehlen.")

    # 4. RAFT (Torchvision)
    print(f"\n[4/4] RAFT (Optical Flow):")
    # RAFT wird meist on-demand geladen, wir prüfen nur den Cache
    raft_files = list(demucs_dir.glob("*raft*"))
    if raft_files:
        print("  ✅ RAFT Gewichte im Cache gefunden.")
    else:
        print("  ⚠️ RAFT nicht im Cache (wird bei Bedarf geladen).")

if __name__ == "__main__":
    check_local_models()
