"""PB Studio — GPU/PyTorch Reparatur-Skript.

Prueft den NVIDIA-Treiber, deinstalliert falsche PyTorch-Versionen,
und installiert die korrekte cu113-Version in .venv310.

Ausfuehrung:
    python scripts/fix_gpu_setup.py          # Diagnose + Reparatur
    python scripts/fix_gpu_setup.py --check  # Nur Diagnose
"""

import argparse
import subprocess
import sys
import os


# Ziel-Konfiguration (Surface Book 2, Treiber 461.40)
TARGET_CUDA = "cu113"
TARGET_TORCH = "1.12.1"
TARGET_TORCHAUDIO = "0.12.1"
TARGET_TORCHVISION = "0.13.1"
TORCH_INDEX = "https://download.pytorch.org/whl/cu113"


def _run(cmd: list[str], check: bool = True, timeout: int = 600) -> subprocess.CompletedProcess:
    print(f"  > {' '.join(cmd)}")
    return subprocess.run(cmd, check=check, timeout=timeout)


def _pip(*args: str, timeout: int = 600) -> subprocess.CompletedProcess:
    return _run([sys.executable, "-m", "pip", *args], timeout=timeout)


def _get_driver_version() -> float:
    """Ermittelt NVIDIA-Treiber-Version via PowerShell."""
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             "Get-CimInstance Win32_VideoController "
             "| Where-Object { $_.Name -match 'NVIDIA' } "
             "| Select-Object -First 1 DriverVersion | Format-List"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        for line in r.stdout.splitlines():
            if "DriverVersion" in line:
                wv = line.split(":", 1)[-1].strip()
                parts = wv.split(".")
                if len(parts) >= 4:
                    combined = parts[-2] + parts[-1]
                    if len(combined) >= 5:
                        nv_str = combined[-5:-2] + "." + combined[-2:]
                        return float(nv_str)
    except (subprocess.TimeoutExpired, OSError, ValueError):
        pass
    return 0.0


def _get_installed_torch() -> tuple[str, str]:
    """Returns (torch_version, cuda_tag)."""
    try:
        r = subprocess.run(
            [sys.executable, "-c", "import torch; print(torch.__version__)"],
            capture_output=True, text=True, timeout=30,
        )
        ver = r.stdout.strip()
        cuda_tag = ver.split("+")[1] if "+" in ver else ""
        return ver, cuda_tag
    except (subprocess.TimeoutExpired, OSError):
        return "", ""


def main():
    parser = argparse.ArgumentParser(description="PB Studio GPU/PyTorch Reparatur")
    parser.add_argument("--check", action="store_true", help="Nur pruefen, nicht reparieren")
    args = parser.parse_args()

    print("=" * 60)
    print("   PB STUDIO - GPU SETUP REPARATUR")
    print("=" * 60)

    # Schritt 1: Treiber pruefen
    print("\n[1/4] NVIDIA-Treiber pruefen...")
    driver = _get_driver_version()
    if driver == 0.0:
        print("  FEHLER: Kein NVIDIA-Treiber erkannt!")
        print("  Bitte zuerst Treiber installieren.")
        sys.exit(1)

    print(f"  Treiber-Version: {driver:.2f}")

    # Schritt 2: PyTorch pruefen
    print("\n[2/4] PyTorch-Installation pruefen...")
    torch_ver, cuda_tag = _get_installed_torch()
    target_full = f"{TARGET_TORCH}+{TARGET_CUDA}"

    if torch_ver:
        print(f"  Installiert: torch {torch_ver}")
        if torch_ver == target_full:
            print(f"  OK: Korrekte Version!")
            _verify_cuda()
            sys.exit(0)
        else:
            print(f"  FALSCH: Erwartet {target_full}")
    else:
        print("  PyTorch nicht installiert.")

    if args.check:
        print("\n  --check Modus: Keine Aenderungen.")
        sys.exit(1)

    # Schritt 3: Reparieren
    print("\n[3/4] PyTorch deinstallieren und neu installieren...")
    _pip("uninstall", "-y", "torch", "torchaudio", "torchvision", check=False)

    packages = [
        f"torch=={TARGET_TORCH}+{TARGET_CUDA}",
        f"torchaudio=={TARGET_TORCHAUDIO}+{TARGET_CUDA}",
        f"torchvision=={TARGET_TORCHVISION}+{TARGET_CUDA}",
    ]
    _pip("install", "--extra-index-url", TORCH_INDEX, *packages, timeout=900)

    # Schritt 4: Verifizieren
    print("\n[4/4] Verifikation...")
    _verify_cuda()


def _verify_cuda():
    """Prueft ob CUDA nach Installation funktioniert."""
    print("  Teste CUDA-Zugriff...")
    r = subprocess.run(
        [sys.executable, "-c", """
import torch
print(f"PyTorch: {torch.__version__}")
print(f"CUDA compiled: {torch.version.cuda}")
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    t = torch.randn(100, 100, device="cuda")
    print(f"GPU Tensor Test: OK ({t.sum().item():.2f})")
else:
    print("WARNUNG: CUDA nicht verfuegbar!")
"""],
        capture_output=True, text=True, timeout=60,
    )
    for line in r.stdout.strip().splitlines():
        print(f"  {line}")

    if "CUDA available: True" in r.stdout:
        print("\n  GPU-SETUP ERFOLGREICH!")
    elif "CUDA available: False" in r.stdout:
        print("\n  WARNUNG: CUDA nicht verfuegbar.")
        print("  - PC neustarten (GPU Error 47?)")
        print("  - GPU_FIX_PERMISSIONS.bat als Admin ausfuehren")


if __name__ == "__main__":
    main()
