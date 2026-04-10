#!/usr/bin/env python3
"""
PB Studio Rebuild - Emergency Legacy Setup
==========================================
Ziel: Höchstmögliche Kompatibilität für Treiber 461.40 unter Python 3.11.
Wir nutzen PyTorch 2.0.1 mit cu117, da dies die stabilste Version ist,
die Python 3.11 unterstützt. Wenn dies fehlschlägt, ist der Treiber
461.40 physisch zu alt für die modernen Bibliotheken der App.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.resolve()
VENV_DIR = PROJECT_DIR / ".venv"
VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"
VENV_PIP = VENV_DIR / "Scripts" / "pip.exe"

# KOMPROMISS: PyTorch 2.0.1 (braucht Python 3.11) + CUDA 11.7
# Falls das nicht geht, ist der Treiber 461.40 das Ende der Fahnenstange.
PYTORCH_INDEX = "https://download.pytorch.org/whl/cu117"
TORCH_PACKAGES = [
    "torch==2.0.1+cu117",
    "torchvision==0.15.2+cu117",
    "torchaudio==2.0.2+cu117",
]

def main():
    print("=== EMERGENCY LEGACY SETUP ===")
    
    if VENV_DIR.exists():
        shutil.rmtree(VENV_DIR, ignore_errors=True)

    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
    subprocess.run([str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip"], check=True)

    print(f"> Installiere PyTorch 2.0.1+cu117 (Letzte Hoffnung für Python 3.11)...")
    subprocess.run([str(VENV_PIP), "install", "--no-cache-dir", "--extra-index-url", PYTORCH_INDEX] + TORCH_PACKAGES, check=True)

    # Restliche App-Dependencies
    with open(PROJECT_DIR / "requirements.txt", "r") as f:
        reqs = [l.strip() for l in f if l.strip() and not l.startswith("#") and "torch" not in l.lower()]
    subprocess.run([str(VENV_PIP), "install"] + reqs, check=True)

    print("\n--- VERIFIKATION ---")
    res = subprocess.run([str(VENV_PYTHON), "-c", "import torch; print(f'CUDA: {torch.cuda.is_available()}'); print(f'Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"FAILED\"}')"], capture_output=True, text=True)
    print(res.stdout)

if __name__ == "__main__":
    main()
