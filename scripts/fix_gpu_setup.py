"""PB Studio — GPU/PyTorch Reparatur-Skript.

Prueft den NVIDIA-Treiber, deinstalliert falsche PyTorch-Versionen,
und installiert die korrekte cu124-Version.

Ausfuehrung:
    python scripts/fix_gpu_setup.py          # Diagnose + Reparatur
    python scripts/fix_gpu_setup.py --check  # Nur Diagnose, keine Aenderungen
"""

import argparse
import subprocess
import sys
import os


# ── Ziel-Konfiguration ─────────────────────────────────────────────────
TARGET_CUDA = "cu124"
TARGET_TORCH = "2.5.1"
TARGET_TORCHAUDIO = "2.5.1"
TARGET_TORCHVISION = "0.20.1"
TORCH_INDEX = "https://download.pytorch.org/whl/cu124"
MIN_DRIVER_VERSION = 550.0  # Fuer CUDA 12.4


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
    """Returns (torch_version, cuda_tag) z.B. ('2.7.1+cu118', 'cu118')."""
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
    print("   PB STUDIO — GPU SETUP REPARATUR")
    print("=" * 60)

    # ── Schritt 1: Treiber pruefen ──────────────────────────────────────
    print("\n[1/4] NVIDIA-Treiber pruefen...")
    driver = _get_driver_version()
    if driver == 0.0:
        print("  FEHLER: Kein NVIDIA-Treiber erkannt!")
        print("  Bitte zuerst Treiber installieren: https://www.nvidia.com/drivers/")
        print("  Nach Installation: PC neustarten, dann dieses Skript erneut ausfuehren.")
        sys.exit(1)

    print(f"  Treiber-Version: {driver:.2f}")
    if driver < MIN_DRIVER_VERSION:
        print(f"  FEHLER: Treiber {driver:.2f} zu alt! Mindestens {MIN_DRIVER_VERSION:.0f} benoetigt.")
        print()
        print("  +------------------------------------------------------+")
        print("  |  NVIDIA-Treiber muss zuerst aktualisiert werden!    |")
        print("  |                                                      |")
        print("  |  1. https://www.nvidia.com/drivers/ oeffnen         |")
        print("  |  2. GPU: GeForce GTX 1060                           |")
        print("  |     OS:  Windows 11                                  |")
        print("  |     Typ: Game Ready oder Studio Driver               |")
        print("  |  3. Treiber herunterladen und installieren           |")
        print("  |  4. PC NEUSTARTEN                                    |")
        print("  |  5. Dieses Skript erneut ausfuehren                 |")
        print("  +------------------------------------------------------+")
        sys.exit(1)

    print(f"  OK: Treiber {driver:.2f} >= {MIN_DRIVER_VERSION:.0f}")

    # ── Schritt 2: Installierte PyTorch-Version pruefen ─────────────────
    print("\n[2/4] PyTorch-Installation pruefen...")
    torch_ver, cuda_tag = _get_installed_torch()
    target_full = f"{TARGET_TORCH}+{TARGET_CUDA}"

    if torch_ver:
        print(f"  Installiert: torch {torch_ver}")
        if torch_ver == target_full:
            print(f"  OK: Korrekte Version bereits installiert!")
            _verify_cuda()
            sys.exit(0)
        else:
            print(f"  FALSCH: Erwartet torch {target_full}")
            if cuda_tag and cuda_tag != TARGET_CUDA:
                print(f"          CUDA-Version: {cuda_tag} statt {TARGET_CUDA}")
    else:
        print("  PyTorch nicht installiert.")

    if args.check:
        print("\n  --check Modus: Keine Aenderungen. Fuehre ohne --check aus fuer Reparatur.")
        sys.exit(1)

    # ── Schritt 3: Falsche Versionen deinstallieren ─────────────────────
    print("\n[3/4] PyTorch deinstallieren und neu installieren...")
    print("  Deinstalliere alte Versionen...")
    _pip("uninstall", "-y", "torch", "torchaudio", "torchvision", check=False)

    # Installiere korrekte Versionen
    print(f"\n  Installiere torch=={TARGET_TORCH}+{TARGET_CUDA} von {TORCH_INDEX}...")
    packages = [
        f"torch=={TARGET_TORCH}+{TARGET_CUDA}",
        f"torchaudio=={TARGET_TORCHAUDIO}+{TARGET_CUDA}",
        f"torchvision=={TARGET_TORCHVISION}+{TARGET_CUDA}",
    ]
    _pip(
        "install",
        "--extra-index-url", TORCH_INDEX,
        *packages,
        timeout=900,  # 15 min — grosse Downloads
    )

    # ── Schritt 4: Verifikation ─────────────────────────────────────────
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
    props = torch.cuda.get_device_properties(0)
    print(f"VRAM: {props.total_memory // (1024**3)} GB")
    # Schnelltest: Tensor auf GPU
    t = torch.randn(100, 100, device="cuda")
    print(f"GPU Tensor Test: OK ({t.sum().item():.2f})")
else:
    print("WARNUNG: CUDA nicht verfuegbar!")
"""],
        capture_output=True, text=True, timeout=60,
    )
    for line in r.stdout.strip().splitlines():
        print(f"  {line}")
    if r.stderr:
        for line in r.stderr.strip().splitlines():
            if "warning" in line.lower() or "error" in line.lower():
                print(f"  WARN: {line.strip()}")

    if "CUDA available: True" in r.stdout:
        print("\n  +------------------------------------------------------+")
        print("  |  GPU-SETUP ERFOLGREICH!                              |")
        print("  |  CUDA ist aktiv. PB Studio kann gestartet werden.    |")
        print("  +------------------------------------------------------+")
    elif "CUDA available: False" in r.stdout:
        print("\n  WARNUNG: CUDA noch nicht verfuegbar.")
        print("  Moegliche Ursachen:")
        print("  - PC muss nach Treiber-Update neugestartet werden")
        print("  - CUDA_VISIBLE_DEVICES Umgebungsvariable blockiert GPU")
        print("  - Treiber-Installation fehlgeschlagen")
    else:
        print("\n  FEHLER bei Verifikation. Ausgabe oben pruefen.")


if __name__ == "__main__":
    main()
