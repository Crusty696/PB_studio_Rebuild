"""PB Studio — Python 3.10 + CUDA GPU Setup.

Erstellt ein neues venv mit Python 3.10 und installiert
torch 1.12.1+cu113 (kompatibel mit Treiber 461.40).

Voraussetzung: Python 3.10 muss installiert sein.
Download: https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe

Ausfuehrung:
    python scripts/setup_py310_gpu.py
"""

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = PROJECT_ROOT / ".venv310"
REQUIREMENTS = PROJECT_ROOT / "requirements-py310-cu113.txt"

# Python 3.10 Suchpfade (Windows)
PY310_CANDIDATES = [
    r"C:\Python310\python.exe",
    r"C:\Python3.10\python.exe",
    os.path.expanduser(r"~\AppData\Local\Programs\Python\Python310\python.exe"),
    r"C:\Program Files\Python310\python.exe",
    r"C:\Program Files (x86)\Python310\python.exe",
]


def find_python310() -> str | None:
    # py launcher
    try:
        r = subprocess.run(
            ["py", "-3.10", "-c", "import sys; print(sys.executable)"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    for p in PY310_CANDIDATES:
        if os.path.isfile(p):
            try:
                r = subprocess.run(
                    [p, "--version"], capture_output=True, text=True, timeout=5,
                )
                if "3.10" in r.stdout:
                    return p
            except (OSError, subprocess.TimeoutExpired):
                pass
    return None


def main():
    print("=" * 60)
    print("   PB STUDIO - Python 3.10 + CUDA GPU Setup")
    print("=" * 60)

    # 1. Python 3.10 finden
    print("\n[1/5] Python 3.10 suchen...")
    py310 = find_python310()
    if not py310:
        print("  FEHLER: Python 3.10 nicht gefunden!")
        print()
        print("  Bitte Python 3.10.11 installieren:")
        print("  https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe")
        print()
        print("  WICHTIG bei Installation:")
        print('  [x] "Add Python 3.10 to PATH" ankreuzen')
        print('  [x] "Install for all users" ankreuzen')
        print()
        print("  Danach dieses Skript erneut ausfuehren.")
        sys.exit(1)

    print(f"  Gefunden: {py310}")
    r = subprocess.run([py310, "--version"], capture_output=True, text=True)
    print(f"  Version:  {r.stdout.strip()}")

    # 2. Neues venv erstellen
    print(f"\n[2/5] Erstelle venv in {VENV_DIR}...")
    if VENV_DIR.exists():
        print(f"  {VENV_DIR} existiert bereits.")
        resp = input("  Loeschen und neu erstellen? [j/N]: ").strip().lower()
        if resp != "j":
            print("  Abgebrochen.")
            sys.exit(0)
        import shutil
        shutil.rmtree(VENV_DIR)

    subprocess.run([py310, "-m", "venv", str(VENV_DIR)], check=True)
    print("  venv erstellt.")

    # pip/setuptools aktualisieren
    pip = str(VENV_DIR / "Scripts" / "pip.exe")
    python = str(VENV_DIR / "Scripts" / "python.exe")

    print("  pip aktualisieren...")
    subprocess.run([python, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
                   check=True, capture_output=True)

    # 3. PyTorch + CUDA installieren
    print("\n[3/5] Installiere PyTorch 1.12.1+cu113...")
    print("  (torch + torchaudio + torchvision fuer CUDA 11.3)")
    torch_pkgs = [
        "torch==1.12.1+cu113",
        "torchaudio==0.12.1+cu113",
        "torchvision==0.13.1+cu113",
    ]
    subprocess.run(
        [pip, "install", "--extra-index-url", "https://download.pytorch.org/whl/cu113"] + torch_pkgs,
        check=True, timeout=900,
    )

    # 4. Schnelltest CUDA
    print("\n[4/5] CUDA-Schnelltest...")
    r = subprocess.run(
        [python, "-c", """
import torch
print(f"PyTorch: {torch.__version__}")
print(f"CUDA compiled: {torch.version.cuda}")
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    t = torch.randn(10, 10, device="cuda")
    print(f"GPU Tensor: OK")
else:
    print("WARNUNG: CUDA nicht verfuegbar!")
    print("Moegliche Ursache: Treiber 461.40 ist knapp unter cu113-Minimum (465.89)")
    print("Fallback: Python 3.9 + cu111 waere noetig.")
"""],
        capture_output=True, text=True, timeout=60,
    )
    for line in r.stdout.strip().splitlines():
        print(f"  {line}")
    if r.stderr:
        for line in r.stderr.strip().splitlines():
            if "error" in line.lower() or "warning" in line.lower():
                print(f"  WARN: {line.strip()[:100]}")

    cuda_ok = "CUDA available: True" in r.stdout

    if not cuda_ok:
        print()
        print("  +------------------------------------------------------+")
        print("  |  CUDA funktioniert NICHT mit cu113 + Treiber 461.40  |")
        print("  |                                                      |")
        print("  |  Naechster Schritt:                                  |")
        print("  |  Python 3.9 + cu111 versuchen (100% kompatibel)      |")
        print("  |  Oder Treiber-Update pruefen.                        |")
        print("  +------------------------------------------------------+")
        sys.exit(1)

    # 5. Restliche Pakete installieren
    print("\n[5/5] Installiere App-Abhaengigkeiten...")
    if REQUIREMENTS.exists():
        subprocess.run(
            [pip, "install", "-r", str(REQUIREMENTS),
             "--extra-index-url", "https://download.pytorch.org/whl/cu113"],
            check=True, timeout=900,
        )
    else:
        print(f"  WARNUNG: {REQUIREMENTS} nicht gefunden!")
        print("  Bitte manuell installieren:")
        print(f"  {pip} install -r requirements-py310-cu113.txt")

    print()
    print("  +------------------------------------------------------+")
    print("  |  SETUP ERFOLGREICH!                                  |")
    print("  |                                                      |")
    print("  |  App starten mit:                                    |")
    print("  |  .venv310\\Scripts\\python.exe main.py                 |")
    print("  +------------------------------------------------------+")


if __name__ == "__main__":
    main()
