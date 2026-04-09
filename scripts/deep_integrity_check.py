
import logging
import torch
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DeepCheck")

def test_models():
    print("\n" + "="*60)
    print("  PB STUDIO - DEEP MODEL INTEGRITY CHECK")
    print("="*60)
    
    # 1. CUDA Check
    if not torch.cuda.is_available():
        print("[FAIL] CUDA nicht verfügbar! Analyse unmöglich.")
        return
    print(f"[OK] GPU erkannt: {torch.cuda.get_device_name(0)}")

    # 2. Demucs Check
    try:
        from demucs.pretrained import get_model
        print("[...] Prüfe Demucs (htdemucs_ft)...")
        # Wir laden nur die Metadaten, um VRAM zu sparen, aber den Import zu testen
        m = get_model("htdemucs_ft")
        print(f"[OK] Demucs Modell-Definition gefunden (Sources: {m.sources})")
    except Exception as e:
        print(f"[FAIL] Demucs Fehler: {e}")

    # 3. SigLIP Check
    try:
        from transformers import AutoProcessor, AutoModel
        model_id = "google/siglip-so400m-patch14-384"
        print(f"[...] Prüfe SigLIP Tokenizer/Processor...")
        # Nur Config laden um Existenz zu prüfen
        proc = AutoProcessor.from_pretrained(model_id)
        print(f"[OK] SigLIP Processor/SentencePiece bereit.")
    except Exception as e:
        print(f"[FAIL] SigLIP/Transformers Fehler: {e}")

    # 4. beat_this Check
    try:
        import beat_this
        print("[OK] beat_this Bibliothek importierbar.")
    except Exception as e:
        print(f"[FAIL] beat_this Fehler: {e}")

    # 5. Faster-Whisper Check
    try:
        from faster_whisper import WhisperModel
        print("[OK] faster-whisper Bibliothek importierbar.")
    except Exception as e:
        print(f"[FAIL] Whisper Fehler: {e}")

    # 6. RAFT Check
    try:
        from torchvision.models.optical_flow import raft_small
        m = raft_small(pretrained=False) # Nur Struktur prüfen
        print("[OK] torchvision RAFT Architektur verfügbar.")
    except Exception as e:
        print(f"[FAIL] Torchvision/RAFT Fehler: {e}")

    print("\n" + "="*60)
    print("  CHECK ABGESCHLOSSEN")
    print("="*60)

if __name__ == "__main__":
    test_models()
